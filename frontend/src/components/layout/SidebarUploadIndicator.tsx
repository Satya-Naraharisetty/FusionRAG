import React, { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpFromLine } from "lucide-react";
import { useUploadQueue } from "../../context/UploadQueueContext";
import { useDocuments } from "../../hooks/useDocuments";
import { rowProgress } from "../../lib/uploadStages";
import { cn } from "../../lib/utils";

/**
 * Mini upload-queue indicator for the sidebar, visible from any page while
 * uploads are in flight. The queue lives in the app-level UploadQueueContext,
 * so it survives navigation; this surface links back to the Documents page
 * where the full queue renders.
 *
 * Expanded: a compact strip with count + live progress bar (processing rows
 * derive their stage from server state, same as the dropzone's batch summary).
 * Collapsed: a dedicated icon button with a count badge.
 */
export const SidebarUploadIndicator: React.FC<{ collapsed: boolean }> = ({ collapsed }) => {
  const navigate = useNavigate();
  const { queue, embeddingStatus } = useUploadQueue();
  const { data: documents = [] } = useDocuments();

  const docById = useMemo(() => new Map(documents.map((d) => [d.id, d])), [documents]);

  const summary = useMemo(() => {
    // Everything not yet done needs attention: queued/uploading/paused rows,
    // rows still processing server-side, and failures waiting to be dismissed.
    const active = queue.filter((q) => q.status !== "completed");
    if (active.length === 0) return null;

    const totalProgress = active.reduce((sum, q) => {
      const doc = q.documentId ? docById.get(q.documentId) : undefined;
      const emb = q.documentId ? embeddingStatus[q.documentId] : undefined;
      return sum + rowProgress(q.status, q.progress, doc, emb, q.startedAt ?? null);
    }, 0);

    return {
      count: active.length,
      progress: Math.round(totalProgress / active.length),
      hasError: active.some((q) => q.status === "error"),
    };
  }, [queue, docById, embeddingStatus]);

  if (!summary) return null;

  const openQueue = () => navigate("/documents");
  const label = `${summary.count} upload${summary.count === 1 ? "" : "s"} in the queue · ${summary.progress}%`;
  const accent = summary.hasError ? "var(--accent-error)" : "var(--accent-primary)";

  if (collapsed) {
    return (
      <button
        onClick={openQueue}
        className="relative w-10 h-10 bg-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] rounded-[var(--radius-lg)] flex items-center justify-center cursor-pointer transition-colors"
        aria-label={label}
        title={label}
      >
        <ArrowUpFromLine size={16} />
        <span
          className="absolute -bottom-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[9px] font-bold text-white"
          style={{ backgroundColor: accent }}
          aria-hidden="true"
        >
          {summary.count}
        </span>
      </button>
    );
  }

  return (
    <button
      onClick={openQueue}
      className="w-full bg-[var(--bg-tertiary)]/50 hover:bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded-[var(--radius-lg)] px-2.5 py-2 text-left cursor-pointer transition-colors"
      aria-label={label}
      title="Open upload queue"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--text-secondary)]">
          <ArrowUpFromLine size={11} style={{ color: accent }} />
          Uploads
        </span>
        <span className="text-[10px] font-mono font-medium text-[var(--text-muted)]">
          {summary.count} · {summary.progress}%
        </span>
      </div>
      <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
        <div
          className={cn(
            "h-1 rounded-full transition-all duration-300",
            summary.hasError
              ? "bg-[var(--accent-error)]"
              : "bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-success)]",
          )}
          style={{ width: `${summary.progress}%` }}
        />
      </div>
    </button>
  );
};

export default SidebarUploadIndicator;
