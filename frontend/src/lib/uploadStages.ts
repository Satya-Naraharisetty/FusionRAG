import { type Document, type DocumentStatus, type EmbeddingStatus } from "../types";

/** How often the queue polls embedding status once chunking has finished. */
export const EMBEDDING_POLL_INTERVAL_MS = 4000;

/**
 * Shared failure copy for the vector-DB stage, so the queue rows, grid cards,
 * and chat attachments all show the same guidance.
 */
export const VECTORIZATION_FAILED_MESSAGE = "Vectorization failed — try regenerating embeddings.";

/**
 * Progress of a single queue row: `processing` rows derive their value from
 * live server state (chunking stage / vector-DB counts), everything else uses
 * its stored percentage. Shared by the queue's batch summary and the sidebar
 * indicator so the two surfaces can't drift apart.
 */
export function rowProgress(
  status: string,
  progress: number,
  doc: Document | undefined,
  embedding: EmbeddingStatus | undefined,
  startedAt: number | null,
): number {
  if (status === "processing") {
    return deriveUploadStage(doc?.status, embedding, startedAt).progress;
  }
  return progress;
}

/**
 * True when a document chunked successfully but its embedding job failed — the
 * file is on disk but unsearchable. Distinct from the pipeline failing: the
 * document itself is `completed`, so this is a separate sub-status surfaced
 * via the embedding-status endpoint (which is why `getDocumentProcessingStep`
 * returns null here — the doc is not busy, it's stuck).
 */
export function isVectorizationFailed(
  doc: Document,
  embedding: EmbeddingStatus | undefined,
): boolean {
  return doc.status === "completed" && embedding?.status === "failed";
}

/**
 * Grace period after the upload resolves before a row whose document never
 * surfaces in the list (e.g. it was deleted) is considered stale.
 */
export const STALE_DOC_GRACE_MS = 30_000;

export interface UploadStage {
  /** 0-100 value for the progress ring, derived from real server state. */
  progress: number;
  /** One-line step description shown as the footer under the ring. */
  detail: string;
}

/**
 * Sub-steps of the server-side chunking pipeline. The API only exposes a coarse
 * `processing` status while `DocumentProcessingService` runs, so the footer
 * cycles through the actual pipeline phases as time passes (each is a truthful
 * description of work the pipeline performs).
 */
const CHUNKING_STEPS = [
  "Extracting text…",
  "Cleaning text…",
  "Extracting metadata…",
  "Chunking…",
  "Saving chunks…",
];

const STEP_DURATION_MS = 2600;

function chunkingStep(startedAt: number | null): string {
  if (!startedAt) return CHUNKING_STEPS[0];
  const elapsed = Date.now() - startedAt;
  // Clamp both ends: server/client clock skew can make `elapsed` negative
  // (the server's processing_started_at is in the future), which would index
  // CHUNKING_STEPS[-1] and render "undefined".
  const idx = Math.max(
    0,
    Math.min(Math.floor(elapsed / STEP_DURATION_MS), CHUNKING_STEPS.length - 1),
  );
  return CHUNKING_STEPS[idx];
}

/**
 * Derives the upload-row progress and step footer from the server-side state.
 *
 * The document status tracks the chunking pipeline (pending → processing →
 * completed), while the embedding status — only meaningful once the document is
 * `completed` — tracks the vector-DB stage with real chunk counts.
 */
export function deriveUploadStage(
  docStatus: DocumentStatus | undefined,
  embedding: EmbeddingStatus | undefined,
  startedAt: number | null,
): UploadStage {
  // Upload resolved, but the document hasn't surfaced in the list cache yet.
  if (!docStatus) {
    return {
      progress: 15,
      detail: "Waiting for processing to start…",
    };
  }

  switch (docStatus) {
    case "pending":
      return {
        progress: 15,
        detail: "Uploaded — queued for processing…",
      };
    case "processing":
      return {
        progress: 40,
        detail: chunkingStep(startedAt),
      };
    case "failed":
      return {
        progress: 100,
        detail: "Processing failed — check the document in your library.",
      };
    case "completed":
      break; // fall through to the vector-DB stage
  }

  // Chunks are saved; the embedding job turns them into vector-DB entries.
  if (!embedding || embedding.status === "pending") {
    return {
      progress: 70,
      detail: embedding
        ? "Queued — preparing to index in vector DB…"
        : "Preparing to index in vector DB…",
    };
  }

  if (embedding.status === "generating") {
    const total = embedding.chunks_total || 1;
    const pct = Math.min(95, Math.round(70 + 25 * (embedding.embedded_chunks / total)));
    return {
      progress: pct,
      detail: `Indexing into vector DB — ${embedding.embedded_chunks} of ${embedding.chunks_total} chunks embedded`,
    };
  }

  if (embedding.status === "failed") {
    return {
      progress: 100,
      detail: VECTORIZATION_FAILED_MESSAGE,
    };
  }

  // embedding.status === "completed"
  return {
    progress: 100,
    detail: "Indexed in vector DB — ready to chat",
  };
}

/**
 * Per-document pipeline stage, or null when the document is not being
 * processed. A completed document stays busy until its embedding status
 * resolves to done, so grid cards keep showing the vector-DB step while
 * chunks are still being indexed.
 */
export function getDocumentProcessingStep(
  doc: Document,
  embedding: EmbeddingStatus | undefined,
): UploadStage | null {
  const isBusy =
    doc.status === "pending" ||
    doc.status === "processing" ||
    (doc.status === "completed" &&
      (!embedding || embedding.status === "pending" || embedding.status === "generating"));
  if (!isBusy) return null;

  return deriveUploadStage(
    doc.status,
    doc.status === "completed" ? embedding : undefined,
    doc.processing_started_at ? new Date(doc.processing_started_at).getTime() : null,
  );
}

export interface PipelineSummary {
  /** Documents still being processed (queued, chunking, or vectorizing). */
  processing: number;
  /** Aggregate 0-100 progress across the active documents. */
  progress: number;
  /** One-line step description, or null when nothing is processing. */
  detail: string | null;
}

/**
 * Aggregates per-document pipeline state into a single summary for sidebar
 * surfaces (e.g. the Documents button tooltip). The reported step is the one
 * furthest along (vector DB > chunking > queued), so the tooltip shows the
 * current stage of the whole pipeline rather than the slowest file.
 */
export function summarizeDocumentPipeline(
  documents: Document[],
  embeddingStatus: Record<string, EmbeddingStatus>,
): PipelineSummary {
  const active: UploadStage[] = [];

  for (const doc of documents) {
    const emb = doc.status === "completed" ? embeddingStatus[doc.id] : undefined;
    const stage = getDocumentProcessingStep(doc, emb);
    if (stage) active.push(stage);
  }

  if (active.length === 0) {
    return { processing: 0, progress: 0, detail: null };
  }

  const current = active.reduce((a, b) => (b.progress > a.progress ? b : a));
  const progress = Math.round(
    active.reduce((sum, stage) => sum + stage.progress, 0) / active.length,
  );
  const prefix = active.length > 1 ? `${active.length} files processing · ` : "";

  return {
    processing: active.length,
    progress,
    detail: prefix + current.detail,
  };
}
