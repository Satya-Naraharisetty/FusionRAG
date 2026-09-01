import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  deriveUploadStage,
  getDocumentProcessingStep,
  isVectorizationFailed,
  rowProgress,
  summarizeDocumentPipeline,
} from "../lib/uploadStages";
import { UploadProgress } from "../components/ui/UploadProgress";
import { EmbeddingStatus, Document } from "../types";

const embedding = (overrides: Partial<EmbeddingStatus>): EmbeddingStatus => ({
  status: "pending",
  chunks_total: 0,
  embedded_chunks: 0,
  failed_chunks: 0,
  provider: "test",
  model: "test",
  ...overrides,
});

afterEach(() => {
  vi.useRealTimers();
});

describe("deriveUploadStage", () => {
  it("waits for the doc to surface after the upload resolves", () => {
    const stage = deriveUploadStage(undefined, undefined, null);
    expect(stage.progress).toBe(15);
    expect(stage.detail).toContain("Waiting");
  });

  it("maps a pending document to the queued stage", () => {
    const stage = deriveUploadStage("pending", undefined, null);
    expect(stage.progress).toBe(15);
    expect(stage.detail).toContain("queued");
  });

  it("cycles through the chunking sub-steps by elapsed time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1000);
    const startedAt = 1000;

    expect(deriveUploadStage("processing", undefined, startedAt).detail).toBe("Extracting text…");

    vi.setSystemTime(1000 + 2600 * 3);
    expect(deriveUploadStage("processing", undefined, startedAt).detail).toBe("Chunking…");

    // Past the last sub-step, stays on the final one.
    vi.setSystemTime(1000 + 2600 * 99);
    const last = deriveUploadStage("processing", undefined, startedAt);
    expect(last.detail).toBe("Saving chunks…");
    expect(last.progress).toBe(40);
  });

  it("clamps to the first sub-step when the clock is skewed into the future", () => {
    // The server's processing_started_at can be ahead of the client clock;
    // negative elapsed must not index CHUNKING_STEPS[-1] (would be undefined).
    vi.useFakeTimers();
    vi.setSystemTime(1000);
    const stage = deriveUploadStage(
      "processing",
      undefined,
      1000 + 60_000, // startedAt in the future
    );
    expect(stage.detail).toBe("Extracting text…");
  });

  it("waits on the vector-DB stage once chunking completed", () => {
    const stage = deriveUploadStage("completed", undefined, null);
    expect(stage.progress).toBe(70);
    expect(stage.detail).toContain("vector DB");
  });

  it("shows real embedding progress while generating", () => {
    const stage = deriveUploadStage(
      "completed",
      embedding({ status: "generating", chunks_total: 10, embedded_chunks: 4 }),
      null,
    );
    // 70 + 25 * (4/10) = 80
    expect(stage.progress).toBe(80);
    expect(stage.detail).toContain("4 of 10");
  });

  it("caps vector-DB progress at 95 during generation", () => {
    const stage = deriveUploadStage(
      "completed",
      embedding({ status: "generating", chunks_total: 10, embedded_chunks: 10 }),
      null,
    );
    expect(stage.progress).toBe(95);
  });

  it("reports ready at 100 once embeddings complete", () => {
    const stage = deriveUploadStage(
      "completed",
      embedding({ status: "completed", chunks_total: 10, embedded_chunks: 10 }),
      null,
    );
    expect(stage.progress).toBe(100);
    expect(stage.detail).toContain("ready");
  });

  it("reports failure when vectorization failed", () => {
    const stage = deriveUploadStage(
      "completed",
      embedding({ status: "failed", failed_chunks: 3 }),
      null,
    );
    expect(stage.detail).toContain("failed");
  });

  it("reports failure when the chunking pipeline failed", () => {
    const stage = deriveUploadStage("failed", undefined, null);
    expect(stage.progress).toBe(100);
    expect(stage.detail).toContain("failed");
  });
});

describe("getDocumentProcessingStep", () => {
  const doc = (overrides: Partial<Document>): Document => ({
    id: "doc-1",
    user_id: "u",
    conversation_id: null,
    filename: "a.pdf",
    original_filename: "a.pdf",
    content_type: "application/pdf",
    file_size: 100,
    checksum: "x",
    status: "completed",
    extractor_version: "1.0",
    failure_reason: null,
    page_count: null,
    word_count: null,
    language: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    processing_started_at: null,
    processing_completed_at: null,
    ...overrides,
  });

  it("is null for an indexed document", () => {
    expect(
      getDocumentProcessingStep(doc({ id: "a" }), embedding({ status: "completed" })),
    ).toBeNull();
  });

  it("is null for a failed document", () => {
    expect(getDocumentProcessingStep(doc({ id: "a", status: "failed" }), undefined)).toBeNull();
  });

  it("reports the queued stage for a pending document", () => {
    const step = getDocumentProcessingStep(doc({ id: "a", status: "pending" }), undefined);
    expect(step?.progress).toBe(15);
    expect(step?.detail).toContain("queued");
  });

  it("reports the chunking sub-step for a processing document", () => {
    const step = getDocumentProcessingStep(doc({ id: "a", status: "processing" }), undefined);
    expect(step?.progress).toBe(40);
    expect(step?.detail).toBe("Extracting text…");
  });

  it("stays busy at the vector-DB stage while embeddings are unknown", () => {
    const step = getDocumentProcessingStep(doc({ id: "a" }), undefined);
    expect(step?.progress).toBe(70);
    expect(step?.detail).toContain("vector DB");
  });

  it("reports the queued vector-DB stage when the embedding job is pending", () => {
    const step = getDocumentProcessingStep(doc({ id: "a" }), embedding({ status: "pending" }));
    expect(step?.progress).toBe(70);
    expect(step?.detail).toBe("Queued — preparing to index in vector DB…");
  });

  it("is null when vectorization failed (doc unsearchable but not busy)", () => {
    expect(getDocumentProcessingStep(doc({ id: "a" }), embedding({ status: "failed" }))).toBeNull();
  });

  it("reports real counts while embeddings are generating", () => {
    const step = getDocumentProcessingStep(
      doc({ id: "a" }),
      embedding({ status: "generating", chunks_total: 10, embedded_chunks: 4 }),
    );
    expect(step?.progress).toBe(80);
    expect(step?.detail).toContain("4 of 10");
  });
});

describe("rowProgress", () => {
  it("passes through the stored percentage for non-processing rows", () => {
    expect(rowProgress("uploading", 42, undefined, undefined, null)).toBe(42);
    expect(rowProgress("queued", 0, undefined, undefined, null)).toBe(0);
    expect(rowProgress("completed", 100, undefined, undefined, null)).toBe(100);
    expect(rowProgress("error", 100, undefined, undefined, null)).toBe(100);
  });

  it("derives the live stage for processing rows", () => {
    expect(rowProgress("processing", 0, undefined, undefined, null)).toBe(15);
  });
});

describe("isVectorizationFailed", () => {
  const doc = (overrides: Partial<Document>): Document => ({
    id: "doc-1",
    user_id: "u",
    conversation_id: null,
    filename: "a.pdf",
    original_filename: "a.pdf",
    content_type: "application/pdf",
    file_size: 100,
    checksum: "x",
    status: "completed",
    extractor_version: "1.0",
    failure_reason: null,
    page_count: null,
    word_count: null,
    language: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    processing_started_at: null,
    processing_completed_at: null,
    ...overrides,
  });

  it("is true when chunking completed but the embedding job failed", () => {
    expect(isVectorizationFailed(doc({ id: "a" }), embedding({ status: "failed" }))).toBe(true);
  });

  it("is false while the embedding job is still working or unknown", () => {
    expect(isVectorizationFailed(doc({ id: "a" }), embedding({ status: "pending" }))).toBe(false);
    expect(isVectorizationFailed(doc({ id: "a" }), embedding({ status: "generating" }))).toBe(
      false,
    );
    expect(isVectorizationFailed(doc({ id: "a" }), undefined)).toBe(false);
  });

  it("is false once embeddings completed", () => {
    expect(isVectorizationFailed(doc({ id: "a" }), embedding({ status: "completed" }))).toBe(false);
  });

  it("is false for documents that never reached completed", () => {
    expect(
      isVectorizationFailed(
        doc({ id: "a", status: "processing" }),
        embedding({ status: "failed" }),
      ),
    ).toBe(false);
    expect(
      isVectorizationFailed(doc({ id: "a", status: "failed" }), embedding({ status: "failed" })),
    ).toBe(false);
  });
});

describe("UploadProgress processing state", () => {
  it("renders the step footer beneath the ring", () => {
    render(<UploadProgress progress={40} status="processing" showLabel footer="Chunking…" />);
    expect(screen.getByText("Chunking…")).toBeTruthy();
    expect(screen.getByText("40%")).toBeTruthy();
  });
});

describe("summarizeDocumentPipeline", () => {
  const doc = (overrides: Partial<Document>): Document => ({
    id: "doc-1",
    user_id: "u",
    conversation_id: null,
    filename: "a.pdf",
    original_filename: "a.pdf",
    content_type: "application/pdf",
    file_size: 100,
    checksum: "x",
    status: "completed",
    extractor_version: "1.0",
    failure_reason: null,
    page_count: null,
    word_count: null,
    language: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    processing_started_at: null,
    processing_completed_at: null,
    ...overrides,
  });

  it("is idle with no documents", () => {
    const summary = summarizeDocumentPipeline([], {});
    expect(summary.processing).toBe(0);
    expect(summary.detail).toBeNull();
  });

  it("is idle once everything is indexed", () => {
    const summary = summarizeDocumentPipeline([doc({ id: "a" })], {
      a: embedding({ status: "completed" }),
    });
    expect(summary.processing).toBe(0);
    expect(summary.detail).toBeNull();
  });

  it("reports queued documents", () => {
    const summary = summarizeDocumentPipeline([doc({ id: "a", status: "pending" })], {});
    expect(summary.processing).toBe(1);
    expect(summary.detail).toContain("queued");
  });

  it("reports the chunking sub-step for processing documents", () => {
    const summary = summarizeDocumentPipeline(
      [doc({ id: "a", status: "processing", processing_started_at: null })],
      {},
    );
    expect(summary.detail).toBe("Extracting text…");
  });

  it("reports the vector-DB stage with real counts once chunking finished", () => {
    const summary = summarizeDocumentPipeline([doc({ id: "a", status: "completed" })], {
      a: embedding({ status: "generating", chunks_total: 10, embedded_chunks: 4 }),
    });
    expect(summary.processing).toBe(1);
    expect(summary.progress).toBe(80);
    expect(summary.detail).toContain("4 of 10");
    expect(summary.detail).toContain("vector DB");
  });

  it("counts a completed doc as busy while its embedding status is unknown", () => {
    const summary = summarizeDocumentPipeline([doc({ id: "a" })], {});
    expect(summary.processing).toBe(1);
    expect(summary.detail).toContain("vector DB");
  });

  it("excludes failed documents", () => {
    const summary = summarizeDocumentPipeline([doc({ id: "a", status: "failed" })], {});
    expect(summary.processing).toBe(0);
    expect(summary.detail).toBeNull();
  });

  it("prefixes the count when multiple files are processing", () => {
    const summary = summarizeDocumentPipeline(
      [doc({ id: "a", status: "processing" }), doc({ id: "b", status: "completed" })],
      {
        b: embedding({ status: "generating", chunks_total: 5, embedded_chunks: 2 }),
      },
    );
    expect(summary.processing).toBe(2);
    expect(summary.detail).toContain("2 files processing");
    // The furthest-along step (vector DB at 80) wins over chunking at 40.
    expect(summary.detail).toContain("vector DB");
  });
});
