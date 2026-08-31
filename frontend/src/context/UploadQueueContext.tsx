import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../hooks/useAuth";
import { useDocuments, useUploadDocument } from "../hooks/useDocuments";
import { useEmbeddingStatus } from "../hooks/useEmbeddingStatus";
import { useDocumentStatusMap } from "../hooks/useDocumentStatusMap";
import { documentsApi } from "../api/documents";
import {
  STALE_DOC_GRACE_MS,
  VECTORIZATION_FAILED_MESSAGE,
} from "../lib/uploadStages";
import { QUERY_KEYS, UPLOAD_LIMITS } from "../lib/constants";
import { type EmbeddingStatus } from "../types";
import toast from "react-hot-toast";

export type QueueSource = "documents" | "chat";

export interface QueueFile {
  id: string;
  /** Display name — kept separate from `file` so restored rows (no File object) still render. */
  fileName: string;
  /** Present only for rows that can still upload (queued/paused/retryable). */
  file?: File;
  status: "queued" | "uploading" | "paused" | "processing" | "completed" | "error";
  progress: number;
  controller?: AbortController;
  /** Server-side document id once the HTTP upload resolves. */
  documentId?: string;
  /** When server-side processing began (drives the chunking sub-step cycle). */
  startedAt?: number;
  /** Error detail surfaced under the row when processing fails. */
  detail?: string;
  /**
   * Where the row was created. Chat-composer rows are scoped to a
   * conversation and render only in that composer's tray; document rows
   * render in the Documents-page queue. Both count toward the sidebar
   * indicator and both survive navigation (and reload, once the server knows
   * about the document).
   */
  source: QueueSource;
  /** Chat rows are scoped to the conversation they were attached in. */
  conversationId?: string;
  /** Object URL preview (chat image attachments). Not persisted. */
  preview?: string;
  /** Fired after the HTTP upload succeeds (chat composer feeds "recent files"). Not persisted. */
  onUploaded?: (file: File) => void;
}

/** Options for {@link addFiles} — chat rows override the document defaults. */
export interface AddFilesOptions {
  source?: QueueSource;
  /** Chat rows are scoped to the conversation that created them. */
  conversationId?: string;
  /** Byte cap for validation; defaults to the documents limit (50 MB). */
  maxSize?: number;
  /** Extension list without dots; defaults to the documents formats. */
  acceptedExtensions?: string[];
  /** Start uploading each added row immediately (chat composer behavior). */
  autoUpload?: boolean;
  /** Skip the "Added N files to queue" toast (the composer tray is feedback enough). */
  silent?: boolean;
  getPreview?: (file: File) => string | undefined;
  onUploaded?: (file: File) => void;
}

const DEFAULT_ACCEPTED_EXTENSIONS = ["pdf", "txt", "docx", "doc", "md", "png", "jpg", "jpeg", "webp"];

/**
 * The upload queue is app-level state, not page state: processing continues
 * after the user navigates away, and a reload shouldn't strand in-flight rows.
 * This provider owns the queue and persists a JSON-safe snapshot (rows the
 * server knows about, keyed by user id) so it survives both navigation and
 * full page reloads.
 */

/** JSON-safe subset of a queue row — everything except File/AbortController/callbacks. */
interface SnapshotItem {
  id: string;
  fileName: string;
  status: QueueFile["status"];
  progress: number;
  documentId?: string;
  startedAt?: number;
  detail?: string;
  /** Absent in snapshots written before rows carried a source — restore defaults it. */
  source?: QueueSource;
  conversationId?: string;
}

interface QueueSnapshot {
  v: 1;
  userId: string;
  items: SnapshotItem[];
}

const STORAGE_KEY = "upload-queue-v1";

/**
 * Fields for the snapshot: only rows the server knows about can be restored.
 * Completed rows are never resurrected (restoreableFromSnapshot only takes
 * processing/error) and auto-cleanup drops them shortly after they finish —
 * keep them out of the snapshot entirely.
 */
export function pickSnapshotItems(queue: QueueFile[]): SnapshotItem[] {
  return queue
    .filter((q) => q.documentId && q.status !== "completed")
    .map(
      ({
        id,
        fileName,
        status,
        progress,
        documentId,
        startedAt,
        detail,
        source,
        conversationId,
      }) => ({
        id,
        fileName,
        status,
        progress,
        documentId,
        startedAt,
        detail,
        source,
        conversationId,
      })
    );
}

/**
 * Rows worth resurrecting after a reload, for the snapshot's own user. A
 * reload can't resume queued/uploading/paused rows (the File object is gone)
 * and completed rows are already visible in the grid — only rows still
 * working, or that failed server-side, come back.
 */
export function restoreableFromSnapshot(
  snapshot: QueueSnapshot | null,
  userId: string | undefined
): QueueFile[] {
  if (!snapshot || !userId || snapshot.userId !== userId) return [];
  return snapshot.items
    .filter((i) => i.status === "processing" || i.status === "error")
    .map((i) => ({
      ...i,
      // Snapshots written before rows carried a source default to documents.
      source: i.source ?? "documents",
    }));
}

interface UploadQueueContextValue {
  queue: QueueFile[];
  /** Live embedding status per document id (shared React Query cache). */
  embeddingStatus: Record<string, EmbeddingStatus>;
  addFiles: (files: File[], options?: AddFilesOptions) => QueueFile[];
  startUpload: (itemId: string) => void;
  pauseUpload: (itemId: string) => void;
  cancelUpload: (itemId: string) => void;
  /** Remove rows without aborting in-flight uploads (chat send). Revokes previews. */
  removeItems: (itemIds: string[]) => void;
  clearCompleted: () => void;
  moveItem: (fromIndex: number, toIndex: number) => void;
  /**
   * Drop every chat-composer row scoped to a conversation (used when the
   * conversation is deleted). In-flight uploads are aborted, previews revoked.
   */
  discardConversationRows: (conversationId: string) => void;
  /**
   * Hand deferred chat attachments to a just-created conversation: rows that
   * were queued while their (brand-new) chat had no id yet are reparented,
   * started, and dismissed from the tray — the uploads continue server-side.
   */
  uploadQueuedChatRows: (conversationId: string) => void;
  /**
   * Drop deferred chat rows that never found a conversation (the user left a
   * brand-new chat without sending, so no conversation was ever created).
   * Keeps an abandoned draft's attachments from flushing into a *different*
   * chat later.
   */
  discardQueuedNewChatRows: () => void;
}

// eslint-disable-next-line react-refresh/only-export-components
export const UploadQueueContext = createContext<
  UploadQueueContextValue | undefined
>(undefined);

const revokePreview = (item: QueueFile) => {
  if (item.preview) {
    try {
      URL.revokeObjectURL(item.preview);
    } catch {
      // Not a real object URL / environment without URL support.
    }
  }
};

export interface UploadQueueProviderProps {
  children: React.ReactNode;
  /**
   * Completed document rows auto-dismiss this many ms after they finish — the
   * automated "Clear done". Chat rows keep their composer lifecycle (sent or
   * cancelled). Exposed as a prop so tests can shrink the window.
   */
  completedRowTtlMs?: number;
}

export const UploadQueueProvider: React.FC<UploadQueueProviderProps> = ({
  children,
  completedRowTtlMs = 5000,
}) => {
  const queryClient = useQueryClient();
  const uploadMutation = useUploadDocument();
  // Shares the same query/cache as the Documents page and sidebar: refetches
  // every 5s while any document is pending/processing, so rows track the
  // chunking pipeline live.
  const { data: documents = [], isLoading: documentsLoading } = useDocuments();
  const { user, isLoading: authLoading } = useAuth();
  const userId = user?.id;

  const [queue, setQueue] = useState<QueueFile[]>([]);

  // Chat-scoped documents are deliberately absent from the global documents
  // list, so their rows must reconcile through their own sources: the
  // per-document status poll (failed → error, gone → orphaned) and the
  // embedding-status poll (extra ids) for the vector-DB stage.
  const chatProcessingDocIds = useMemo(
    () =>
      queue
        .filter(
          (q) =>
            q.source === "chat" &&
            q.status === "processing" &&
            Boolean(q.documentId)
        )
        .map((q) => q.documentId as string),
    [queue]
  );
  const embeddingStatus = useEmbeddingStatus(chatProcessingDocIds);
  const chatDocStatusMap = useDocumentStatusMap(chatProcessingDocIds);
  const restoredForRef = useRef<string | null>(null);
  // Set to true by the restore effect when it actually resurrected rows, so
  // the persist effect (same commit, still seeing an empty queue) doesn't
  // wipe the snapshot before the restored rows re-render and get re-written.
  const restoredSnapshotRef = useRef(false);
  // Uploads already started — guards against double-starting the same row
  // (e.g. a fast double-click on "Upload All") before state catches up.
  const inFlightRef = useRef<Set<string>>(new Set());
  // Per-row timers for auto-dismissing completed document rows. Kept in a ref
  // so re-scans of the queue never double-schedule a row.
  const cleanupTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map()
  );

  const docById = useMemo(
    () => new Map(documents.map((d) => [d.id, d])),
    [documents]
  );

  // Keep a ref so action callbacks always read the latest queue.
  const queueRef = useRef<QueueFile[]>([]);
  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);

  /* ── Restore / clear on auth changes ── */
  useEffect(() => {
    // Auth hasn't resolved yet — restoring or wiping the snapshot now would
    // race the login flow (the initial boot would delete it before the user
    // is known). Wait for isLoading to settle.
    if (authLoading) return;
    if (!userId) {
      // Logged out: in-flight work belongs to a session we can't resume.
      queueRef.current.forEach(revokePreview);
      setQueue([]);
      restoredForRef.current = null;
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch {
        // Storage unavailable — nothing to clean.
      }
      return;
    }
    if (restoredForRef.current === userId) return;
    restoredForRef.current = userId;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const snapshot = JSON.parse(raw) as QueueSnapshot;
      if (snapshot.userId !== userId) {
        // Stale snapshot from another account — drop it.
        localStorage.removeItem(STORAGE_KEY);
        return;
      }
      const restored = restoreableFromSnapshot(snapshot, userId);
      if (restored.length > 0) {
        restoredSnapshotRef.current = true;
        setQueue(restored);
      }
    } catch {
      // Corrupt snapshot — ignore.
    }
  }, [userId, authLoading]);

  /* ── Persist the snapshot (best-effort) ── */
  useEffect(() => {
    if (!userId) return;
    const snapshot: QueueSnapshot = {
      v: 1,
      userId,
      items: pickSnapshotItems(queue),
    };
    try {
      if (snapshot.items.length === 0) {
        if (restoredSnapshotRef.current) {
          // Rows were just restored but haven't re-rendered into `queue` yet —
          // don't wipe the snapshot; the next persist run will write them.
          restoredSnapshotRef.current = false;
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      } else {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
      }
    } catch {
      // Storage full/unavailable — persistence is best-effort.
    }
  }, [queue, userId]);

  /* ── Promote rows whose chunking pipeline failed server-side, or whose
     document vanished (deleted) — after a grace period, so the row never
     stalls. Gated on documentsLoading so restored rows aren't prematurely
     marked stale while the documents query is still fetching. `queue` is a
     dependency so rows restored (or added) after the server state resolved
     are still evaluated; the changed-guard keeps this from re-setting state
     when nothing actually changed. ── */
  useEffect(() => {
    if (documentsLoading) return;
    const now = Date.now();
    setQueue((prev) => {
      let changed = false;
      // The explicit QueueFile return annotation keeps the spread + status
      // override from widening the literal to `string` in inference.
      const next = prev.map((item): QueueFile => {
        if (item.status !== "processing" || !item.documentId) return item;
        const doc = docById.get(item.documentId);
        if (doc?.status === "failed") {
          changed = true;
          return {
            ...item,
            status: "error",
            progress: 100,
            detail: doc.failure_reason || "Processing failed",
          };
        }
        if (
          !doc &&
          item.startedAt &&
          now - item.startedAt > STALE_DOC_GRACE_MS
        ) {
          changed = true;
          return {
            ...item,
            status: "error",
            progress: 100,
            detail: "Document was removed before processing finished",
          };
        }
        // Chat-scoped documents are not in the global library — resolve their
        // status through the per-document poll (null = gone, undefined =
        // still loading).
        const scoped = doc ? undefined : chatDocStatusMap?.get(item.documentId);
        if (scoped?.status === "failed") {
          changed = true;
          return {
            ...item,
            status: "error",
            progress: 100,
            detail: scoped.failure_reason || "Processing failed",
          };
        }
        if (
          scoped === null &&
          item.startedAt &&
          now - item.startedAt > STALE_DOC_GRACE_MS
        ) {
          changed = true;
          return {
            ...item,
            status: "error",
            progress: 100,
            detail: "Document was removed before processing finished",
          };
        }
        return item;
      });
      return changed ? next : prev;
    });
  }, [docById, chatDocStatusMap, documentsLoading, queue]);

  /* ── Flip rows to done/error once the shared embedding poll resolves them.
     Polling itself lives in useEmbeddingStatus (React Query, deduped across
     the sidebar, page, and this provider). `queue` is a dependency for the
     same restore-after-resolve reason as above. ── */
  useEffect(() => {
    setQueue((prev) => {
      let changed = false;
      // Same contextual return annotation as the doc-reconciliation effect.
      const next = prev.map((item): QueueFile => {
        if (item.status !== "processing" || !item.documentId) return item;
        const emb = embeddingStatus[item.documentId];
        if (!emb) return item;
        if (emb.status === "completed") {
          changed = true;
          return { ...item, status: "completed", progress: 100 };
        }
        if (emb.status === "failed") {
          changed = true;
          return {
            ...item,
            status: "error",
            progress: 100,
            detail: VECTORIZATION_FAILED_MESSAGE,
          };
        }
        return item;
      });
      return changed ? next : prev;
    });
  }, [embeddingStatus, queue]);

  /* ── Auto-cleanup ("Clear done"): drop completed document rows a few
     seconds after they finish, and with them their snapshot entries. Chat
     rows keep their composer lifecycle (sent or cancelled). The unmount-only
     effect below clears pending timers without resetting them on every queue
     change. ── */
  useEffect(() => {
    const timers = cleanupTimersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  useEffect(() => {
    const timers = cleanupTimersRef.current;
    queue.forEach((item) => {
      if (item.status !== "completed" || item.source === "chat") return;
      if (timers.has(item.id)) return;
      const timer = setTimeout(() => {
        timers.delete(item.id);
        // Changed-guard: the row may already be gone (manual "Clear done")
        // — don't force a re-render for a no-op removal.
        setQueue((prev) => {
          if (!prev.some((q) => q.id === item.id)) return prev;
          return prev.filter((q) => q.id !== item.id);
        });
      }, completedRowTtlMs);
      timers.set(item.id, timer);
    });
  }, [queue, completedRowTtlMs]);

  const runUpload = useCallback(
    async (item: QueueFile) => {
      if (
        inFlightRef.current.has(item.id) ||
        item.status === "uploading" ||
        item.status === "completed" ||
        item.status === "processing" ||
        !item.file
      ) {
        return;
      }
      // Register before any await so a second rapid startUpload call for the
      // same row can't start a duplicate upload.
      inFlightRef.current.add(item.id);
      const controller = new AbortController();
      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id ? { ...q, status: "uploading", controller } : q
        )
      );
      try {
        const uploaded = await uploadMutation.mutateAsync({
          file: item.file,
          // Chat-composer rows carry their conversation so the document is
          // scoped to it (two-tier model) instead of joining the global library.
          conversationId: item.conversationId,
          onProgress: (progressEvent: unknown) => {
            const pe = progressEvent as { loaded: number; total?: number };
            const progress = pe.total
              ? Math.round((pe.loaded * 100) / pe.total)
              : 0;
            setQueue((prev) =>
              prev.map((q) => (q.id === item.id ? { ...q, progress } : q))
            );
          },
          signal: controller.signal,
        });
        // Bytes are uploaded; the backend is now chunking + indexing, tracked
        // through the document list and embedding-status endpoint.
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id
              ? {
                  ...q,
                  status: "processing",
                  progress: 15,
                  documentId: uploaded.id,
                  startedAt: Date.now(),
                }
              : q
          )
        );
        // The composer tray is its own feedback — chat attachments were
        // quiet on success before joining the shared queue, so keep it that
        // way (the error toast and the onUploaded → recents still fire).
        if (item.source !== "chat") {
          toast.success(`Uploaded "${item.fileName}" — processing started`);
        }
        item.onUploaded?.(item.file);
      } catch (err: unknown) {
        const isAborted =
          (err as Error)?.name === "CanceledError" ||
          (err as Error)?.name === "AbortError";
        if (!isAborted) {
          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id
                ? { ...q, status: "error", controller: undefined }
                : q
            )
          );
          toast.error(`Failed to upload "${item.fileName}".`);
        }
      } finally {
        inFlightRef.current.delete(item.id);
      }
    },
    [uploadMutation]
  );

  const startUpload = useCallback(
    (itemId: string) => {
      const item = queueRef.current.find((q) => q.id === itemId);
      if (!item) return;
      void runUpload(item);
    },
    [runUpload]
  );

  const addFiles = useCallback(
    (files: File[], options: AddFilesOptions = {}) => {
      const {
        source = "documents",
        conversationId,
        maxSize = UPLOAD_LIMITS.MAX_FILE_SIZE,
        acceptedExtensions = DEFAULT_ACCEPTED_EXTENSIONS,
        autoUpload = false,
        silent = false,
        getPreview,
        onUploaded,
      } = options;
      const created: QueueFile[] = [];
      files.forEach((file) => {
        if (file.size > maxSize) {
          const maxMB = Math.round(maxSize / (1024 * 1024));
          toast.error(`"${file.name}" exceeds the ${maxMB} MB size limit.`);
          return;
        }
        const ext = file.name.split(".").pop()?.toLowerCase() || "";
        if (!acceptedExtensions.includes(ext)) {
          toast.error(`".${ext}" is not a supported format.`);
          return;
        }
        created.push({
          id: `upload-${Math.random().toString(36).substring(2, 9)}`,
          fileName: file.name,
          file,
          status: "queued",
          progress: 0,
          source,
          ...(conversationId ? { conversationId } : {}),
          ...(getPreview ? { preview: getPreview(file) } : {}),
          ...(onUploaded ? { onUploaded } : {}),
        });
      });
      if (created.length > 0) {
        setQueue((prev) => [...prev, ...created]);
        if (!silent) {
          toast.success(
            `Added ${created.length} file${created.length > 1 ? "s" : ""} to queue.`
          );
        }
        if (autoUpload) {
          // runUpload reads the row passed in (not the still-stale queueRef),
          // so freshly-added rows can start uploading immediately without
          // waiting for the setQueue above to flush.
          created.forEach((item) => void runUpload(item));
        }
      }
      return created;
    },
    [runUpload]
  );

  const pauseUpload = useCallback((itemId: string) => {
    const item = queueRef.current.find((q) => q.id === itemId);
    if (item?.status === "uploading" && item.controller) {
      item.controller.abort();
      setQueue((prev) =>
        prev.map((q) =>
          q.id === itemId
            ? { ...q, status: "paused", controller: undefined }
            : q
        )
      );
    }
  }, []);

  const cancelUpload = useCallback(
    (itemId: string) => {
      const item = queueRef.current.find((q) => q.id === itemId);
      item?.controller?.abort();
      if (item) revokePreview(item);
      if (item?.documentId) {
        void documentsApi.deleteDocument(item.documentId).catch(() => {});
        queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.DOCUMENTS] });
        if (item.conversationId) {
          queryClient.invalidateQueries({
            queryKey: [QUERY_KEYS.DOCUMENTS, "conversation", item.conversationId],
          });
        }
      }
      setQueue((prev) => prev.filter((q) => q.id !== itemId));
    },
    [queryClient]
  );

  const removeItems = useCallback((itemIds: string[]) => {
    const idSet = new Set(itemIds);
    queueRef.current
      .filter((q) => idSet.has(q.id))
      .forEach(revokePreview);
    setQueue((prev) => prev.filter((q) => !idSet.has(q.id)));
  }, []);

  const clearCompleted = useCallback(() => {
    // Scoped to document rows: "Clear done" lives on the Documents queue, and
    // chat-tray rows are dismissed by sending the message or cancelling them.
    const removed = queueRef.current.filter(
      (q) => q.status === "completed" && q.source !== "chat"
    );
    removed.forEach(revokePreview);
    setQueue((prev) =>
      prev.filter((q) => !(q.status === "completed" && q.source !== "chat"))
    );
  }, []);

  const moveItem = useCallback((fromIndex: number, toIndex: number) => {
    setQueue((prev) => {
      if (
        fromIndex === toIndex ||
        fromIndex < 0 ||
        toIndex >= prev.length ||
        fromIndex >= prev.length
      ) {
        return prev;
      }
      const updated = [...prev];
      const [item] = updated.splice(fromIndex, 1);
      updated.splice(toIndex, 0, item);
      return updated;
    });
  }, []);

  const discardConversationRows = useCallback((conversationId: string) => {
    const removed = queueRef.current.filter(
      (q) =>
        q.source === "chat" &&
        (q.conversationId ?? null) === conversationId
    );
    if (removed.length === 0) return;
    // The conversation (and its documents) are being deleted server-side —
    // abort any in-flight uploads for its rows and release their previews.
    // The backend cascade (delete_documents_by_conversation) is the backstop
    // for the residual race where an in-flight upload POST lands after the
    // cascade ran (orphaned doc with a deleted conversation_id) — not
    // resolvable client-side.
    removed.forEach((q) => q.controller?.abort());
    removed.forEach(revokePreview);
    setQueue((prev) =>
      prev.filter(
        (q) =>
          !(q.source === "chat" && (q.conversationId ?? null) === conversationId)
      )
    );
  }, []);

  const uploadQueuedChatRows = useCallback(
    (conversationId: string) => {
      // Deferred rows: chat attachments added while their brand-new chat had
      // no id yet (the backend creates the conversation on the first message).
      // Hand them to the now-known conversation, then dismiss them from the
      // tray — same "uploads continue server-side" semantics as send.
      const rows = queueRef.current.filter(
        (q) => q.source === "chat" && !q.conversationId && q.status === "queued"
      );
      if (rows.length === 0) return;
      setQueue((prev) =>
        prev.filter(
          (q) =>
            !(q.source === "chat" && !q.conversationId && q.status === "queued")
        )
      );
      rows.forEach((row) => void runUpload({ ...row, conversationId }));
    },
    [runUpload]
  );

  const discardQueuedNewChatRows = useCallback(() => {
    const removed = queueRef.current.filter(
      (q) => q.source === "chat" && !q.conversationId && q.status === "queued"
    );
    if (removed.length === 0) return;
    removed.forEach(revokePreview);
    setQueue((prev) =>
      prev.filter(
        (q) =>
          !(q.source === "chat" && !q.conversationId && q.status === "queued")
      )
    );
  }, []);

  const value = useMemo<UploadQueueContextValue>(
    () => ({
      queue,
      embeddingStatus,
      addFiles,
      startUpload,
      pauseUpload,
      cancelUpload,
      removeItems,
      clearCompleted,
      moveItem,
      discardConversationRows,
      uploadQueuedChatRows,
      discardQueuedNewChatRows,
    }),
    [
      queue,
      embeddingStatus,
      addFiles,
      startUpload,
      pauseUpload,
      cancelUpload,
      removeItems,
      clearCompleted,
      moveItem,
      discardConversationRows,
      uploadQueuedChatRows,
      discardQueuedNewChatRows,
    ]
  );

  return (
    <UploadQueueContext.Provider value={value}>
      {children}
    </UploadQueueContext.Provider>
  );
};

export function useUploadQueue(): UploadQueueContextValue {
  const ctx = useContext(UploadQueueContext);
  if (!ctx) {
    throw new Error("useUploadQueue must be used within an UploadQueueProvider");
  }
  return ctx;
}
