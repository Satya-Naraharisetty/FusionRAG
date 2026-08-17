import React, { useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  X,
  AlertCircle,
  Play,
  Pause,
  ArrowUp,
  GripVertical,
  CheckCircle2,
} from "lucide-react";
import { useDocuments } from "../../hooks/useDocuments";
import {
  useUploadQueue,
  type QueueFile,
} from "../../context/UploadQueueContext";
import { deriveUploadStage, rowProgress } from "../../lib/uploadStages";
import { UPLOAD_LIMITS } from "../../lib/constants";
import { type Document, type EmbeddingStatus } from "../../types";
import { Button } from "../ui/Button";
import { FileTypeBadge } from "../ui/FileTypeBadge";
import { UploadProgress } from "../ui/UploadProgress";
import toast from "react-hot-toast";

/**
 * Progress widget for one queue row. While the row is `processing` the ring +
 * footer are derived from live server state (document status for chunking,
 * embedding status for the vector-DB stage) instead of a stored percentage.
 */
const UploadRowProgress: React.FC<{
  item: QueueFile;
  docById: Map<string, Document>;
  embeddingStatus: Record<string, EmbeddingStatus>;
}> = ({ item, docById, embeddingStatus }) => {
  if (item.status === "processing") {
    const doc = item.documentId ? docById.get(item.documentId) : undefined;
    const emb = item.documentId ? embeddingStatus[item.documentId] : undefined;
    const stage = deriveUploadStage(doc?.status, emb, item.startedAt ?? null);
    return (
      <UploadProgress
        progress={stage.progress}
        status="processing"
        size="sm"
        showLabel
        footer={stage.detail}
      />
    );
  }
  return (
    <UploadProgress
      progress={item.progress}
      status={item.status}
      size="sm"
      showLabel
      footer={item.detail}
    />
  );
};

export const UploadDropzone: React.FC = () => {
  // The queue lives in UploadQueueContext (mounted at app root), so in-flight
  // uploads and their progress survive navigation between pages.
  const {
    queue,
    embeddingStatus,
    addFiles,
    startUpload,
    pauseUpload,
    cancelUpload,
    clearCompleted,
    moveItem,
  } = useUploadQueue();
  // Shares the same query/cache as the Documents page: refetches every 5s
  // while any document is pending/processing, so rows track the chunking
  // pipeline live.
  const { data: documents = [] } = useDocuments();
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);

  const docById = useMemo(
    () => new Map(documents.map((d) => [d.id, d])),
    [documents]
  );

  // Chat-composer attachments share the same app-level queue (so they survive
  // navigation), but this Documents queue only renders document rows.
  const docQueue = useMemo(
    () => queue.filter((q) => q.source !== "chat"),
    [queue]
  );
  // The sidebar indicator counts chat uploads too and links here — surface
  // them so a click-through never lands on a confusingly empty queue.
  const activeChatCount = useMemo(
    () => queue.filter((q) => q.source === "chat" && q.status !== "completed").length,
    [queue]
  );

  // An error row without `detail` is a plain upload failure (safe to retry);
  // one with `detail` failed server-side, so retrying would duplicate the
  // document — those are only cancellable from the queue.
  const isRetryableError = (q: QueueFile) => q.status === "error" && !q.detail;

  const uploadAll = () => {
    const pending = docQueue.filter(
      (q) => q.status === "queued" || q.status === "paused" || isRetryableError(q)
    );
    if (pending.length === 0) {
      toast.error("No pending files to upload.");
      return;
    }
    pending.forEach((item) => startUpload(item.id));
  };

  const batchSummary = useMemo(() => {
    if (docQueue.length === 0) return { completed: 0, total: 0, overallProgress: 0 };
    const completed = docQueue.filter((q) => q.status === "completed").length;
    const totalProgress = docQueue.reduce((sum, q) => {
      const doc = q.documentId ? docById.get(q.documentId) : undefined;
      const emb = q.documentId ? embeddingStatus[q.documentId] : undefined;
      return sum + rowProgress(q.status, q.progress, doc, emb, q.startedAt ?? null);
    }, 0);
    return { completed, total: docQueue.length, overallProgress: Math.round(totalProgress / docQueue.length) };
  }, [docQueue, docById, embeddingStatus]);

  const handleDragStart = (idx: number) => setDraggedIdx(idx);

  const handleDragOver = (e: React.DragEvent, targetIdx: number) => {
    e.preventDefault();
    if (draggedIdx === null || draggedIdx === targetIdx) return;
    // The queue is shared with chat rows; map this surface's (filtered)
    // indices back to the full queue before reordering.
    const fromOriginal = queue.findIndex((q) => q.id === docQueue[draggedIdx]?.id);
    const toOriginal = queue.findIndex((q) => q.id === docQueue[targetIdx]?.id);
    if (fromOriginal === -1 || toOriginal === -1) return;
    moveItem(fromOriginal, toOriginal);
    setDraggedIdx(targetIdx);
  };

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop: (accepted) => addFiles(accepted),
    maxSize: UPLOAD_LIMITS.MAX_FILE_SIZE,
    accept: UPLOAD_LIMITS.ACCEPTED_TYPES,
  });

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`group rounded-[var(--radius-2xl)] p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200 ${
          isDragActive
            ? "border-2 border-dashed border-[var(--accent-primary)]/70 bg-[var(--accent-primary)]/8"
            : "border border-dashed border-[var(--border-default)] bg-transparent hover:border-[var(--border-hover)] hover:bg-[var(--bg-secondary)]"
        }`}
      >
        <input {...getInputProps()} />
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-[var(--text-muted)] mb-3 group-hover:text-[var(--text-secondary)] transition-colors">
          <Upload size={16} />
        </div>
        <p className="text-sm font-medium text-[var(--text-primary)] mb-1">
          {isDragActive ? "Drop files here…" : "Drag & drop files here"}
        </p>
        <p className="text-xs text-[var(--text-muted)]">
          PDF, TXT, DOCX, MD, PNG, JPG, WEBP · max 50 MB
        </p>
      </div>

      {/* File rejections */}
      {fileRejections.length > 0 && (
        <div className="flex items-center gap-2 rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3 text-xs font-medium text-[var(--text-secondary)]">
          <AlertCircle size={14} className="flex-shrink-0 text-[var(--accent-error)]" />
          <span>Some files were rejected (too large or unsupported format).</span>
        </div>
      )}

      {/* Chat-composer uploads share this queue but render in the composer
          tray — note them so the sidebar indicator's link isn't a dead end. */}
      {activeChatCount > 0 && docQueue.length === 0 && (
        <p className="flex items-center gap-1.5 px-1 text-[11px] text-[var(--text-muted)]">
          <Upload size={11} className="shrink-0" />
          {activeChatCount} upload{activeChatCount === 1 ? "" : "s"} in progress from the chat
          composer — back in the conversation to see them.
        </p>
      )}

      {/* Upload queue (document rows only — chat attachments live in the composer tray) */}
      {docQueue.length > 0 && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-2xl)] p-4 space-y-3">
          {/* Queue header */}
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                  Upload Queue ({docQueue.length})
                </h4>
                {batchSummary.completed === batchSummary.total && (
                  <span className="flex items-center gap-1 text-[11px] font-medium text-[var(--accent-success)]">
                    <CheckCircle2 size={11} /> All done
                  </span>
                )}
              </div>
              <p className="text-[11px] text-[var(--text-muted)] font-mono mt-0.5">
                {batchSummary.completed}/{batchSummary.total} completed · {batchSummary.overallProgress}%
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              {batchSummary.completed > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearCompleted}
                  className="text-xs"
                  title="Remove completed rows"
                >
                  Clear done
                </Button>
              )}
              {docQueue.some((q) => ["queued", "paused"].includes(q.status) || isRetryableError(q)) && (
                <Button size="sm" onClick={uploadAll} className="gap-1.5 text-xs">
                  <ArrowUp size={12} />
                  Upload All
                </Button>
              )}
            </div>
          </div>

          {/* Batch progress bar */}
          <div className="w-full bg-[var(--bg-tertiary)] rounded-full h-1 overflow-hidden">
            <div
              className="h-1 rounded-full bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-success)] transition-all duration-300"
              style={{ width: `${batchSummary.overallProgress}%` }}
            />
          </div>

          {/* File rows */}
          <div className="space-y-1.5 pt-1">
            {docQueue.map((item, idx) => (
              <div
                key={item.id}
                draggable="true"
                onDragStart={() => handleDragStart(idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragEnd={() => setDraggedIdx(null)}
                className="flex items-center justify-between gap-3 p-3 bg-[var(--bg-tertiary)]/40 hover:bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] transition-colors duration-150"
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  <div
                    className="cursor-grab active:cursor-grabbing text-[var(--text-muted)] hover:text-[var(--text-secondary)] flex-shrink-0"
                    title="Reorder"
                  >
                    <GripVertical size={13} />
                  </div>

                  <FileTypeBadge filename={item.fileName} variant="card" className="w-8 h-8 flex-shrink-0" />

                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium text-[var(--text-primary)] truncate">
                        {item.fileName}
                      </p>
                      <FileTypeBadge filename={item.fileName} variant="minimal" size="sm" className="flex-shrink-0" />
                    </div>
                    <UploadRowProgress
                      item={item}
                      docById={docById}
                      embeddingStatus={embeddingStatus}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-0.5 flex-shrink-0">
                  {item.status === "uploading" && (
                    <Button
                      variant="ghost"
                      size="iconSm"
                      onClick={() => pauseUpload(item.id)}
                      className="h-7 w-7"
                      title="Pause"
                      aria-label="Pause upload"
                    >
                      <Pause size={11} />
                    </Button>
                  )}
                  {item.status === "paused" && (
                    <Button
                      variant="ghost"
                      size="iconSm"
                      onClick={() => startUpload(item.id)}
                      className="h-7 w-7"
                      title="Resume"
                      aria-label="Resume upload"
                    >
                      <Play size={11} className="fill-current" />
                    </Button>
                  )}
                  {item.status === "processing" && (
                    <span
                      className="relative flex h-2 w-2 flex-shrink-0 mx-0.5"
                      title="Processing in the background"
                      aria-hidden="true"
                    >
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent-primary)]/40" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent-primary)]" />
                    </span>
                  )}
                  {item.status !== "completed" && item.status !== "processing" && (
                    <Button
                      variant="ghost"
                      size="iconSm"
                      onClick={() => cancelUpload(item.id)}
                      className="h-7 w-7 hover:text-[var(--accent-error)]"
                      title="Cancel"
                      aria-label="Cancel upload"
                    >
                      <X size={11} />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default UploadDropzone;
