import React, { useState } from "react";
import {
  MoreVertical,
  RefreshCw,
  Trash,
  Database,
  Calendar,
  Layers,
  CheckSquare,
  Square,
  GripVertical,
  Copy,
  Download,
  FolderOpen,
  Eye,
  AlertTriangle,
} from "lucide-react";
import { Document } from "../../types";
import { UploadStage, VECTORIZATION_FAILED_MESSAGE } from "../../lib/uploadStages";
import { FileTypeBadge } from "../ui/FileTypeBadge";
import { formatBytes, relativeTime, cn } from "../../lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuSeparator,
} from "../ui/Dropdown";
import { Button } from "../ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/Modal";

interface DocumentCardProps {
  document: Document;
  /** Current ingestion-pipeline step (Extracting/Chunking/Indexing…), or null when idle. */
  processingStep?: UploadStage | null;
  /** True when chunking finished but the embedding job failed — shows the amber regenerate banner. */
  embeddingFailed?: boolean;
  onDelete: (id: string) => Promise<unknown>;
  onReprocess: (id: string) => Promise<unknown>;
  onRegenerateEmbeddings: (id: string) => Promise<unknown>;
  isSelected: boolean;
  onSelectToggle: () => void;
  documentFolders: { id: string; name: string }[];
  currentFolderId?: string;
  onMoveToFolder: (folderId: string | null) => void;
  onDuplicate: () => void;
  onExport: () => void;
  onDragStart?: (e: React.DragEvent) => void;
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
}

const STATUS_CLASSES: Record<Document["status"], string> = {
  pending:    "bg-amber-500/10   text-amber-400   border border-amber-500/20",
  processing: "bg-blue-500/10    text-blue-400    border border-blue-500/20",
  completed:  "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  failed:     "bg-red-500/10     text-red-400     border border-red-500/20",
};

export const DocumentCard: React.FC<DocumentCardProps> = ({
  document,
  processingStep = null,
  embeddingFailed = false,
  onDelete,
  onReprocess,
  onRegenerateEmbeddings,
  isSelected,
  onSelectToggle,
  documentFolders,
  currentFolderId,
  onMoveToFolder,
  onDuplicate,
  onExport,
  onDragStart,
  onDragOver,
  onDrop,
}) => {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting]             = useState(false);
  const [isRegenerating, setIsRegenerating]     = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(document.id);
      setShowDeleteDialog(false);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleRegenerate = async () => {
    setIsRegenerating(true);
    try {
      await onRegenerateEmbeddings(document.id);
    } finally {
      setIsRegenerating(false);
    }
  };

  return (
    <>
      <div
        draggable="true"
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDrop={onDrop}
        className={cn(
          "group flex flex-col bg-[var(--bg-secondary)] border rounded-[var(--radius-xl)] transition-all duration-200 overflow-hidden select-none",
          isSelected
            ? "border-[var(--accent-primary)]/40 ring-1 ring-[var(--accent-primary)]/20"
            : "border-[var(--border-subtle)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-tertiary)]/40"
        )}
      >
        <div className="p-[calc(var(--space-factor,1)*16px)] flex flex-col gap-[calc(var(--space-factor,1)*12px)] h-full">
          {/* Header: drag handle, checkbox, type badge, title */}
          <div className="flex items-start gap-2">
            <div className="flex items-center gap-1 flex-shrink-0 pt-0.5">
              <div
                className="cursor-grab active:cursor-grabbing text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors p-0.5"
                title="Drag to reorder"
              >
                <GripVertical size={13} />
              </div>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onSelectToggle(); }}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer p-0.5 transition-colors"
                aria-label={isSelected ? "Deselect document" : "Select document"}
              >
                {isSelected
                  ? <CheckSquare size={14} className="text-[var(--accent-primary)]" />
                  : <Square size={14} />
                }
              </button>
            </div>

            <FileTypeBadge
              filename={document.original_filename}
              contentType={document.content_type}
              variant="card"
              className="w-9 h-9 flex-shrink-0"
            />

            <div className="min-w-0 flex-1">
              <h4
                className="text-xs font-semibold text-[var(--text-primary)] truncate leading-snug"
                title={document.original_filename}
              >
                {document.original_filename}
              </h4>
              <p className="text-[11px] text-[var(--text-muted)] font-medium mt-0.5">
                {formatBytes(document.file_size)}
              </p>
            </div>

            {/* Options menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="iconSm"
                  className="flex-shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  aria-label="Document options"
                >
                  <MoreVertical size={13} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger className="gap-2 cursor-pointer">
                    <FolderOpen size={12} />
                    <span>Move to Folder</span>
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent className="w-44">
                    <DropdownMenuItem
                      onClick={() => onMoveToFolder(null)}
                      className="cursor-pointer"
                    >
                      <span className={!currentFolderId ? "font-semibold text-[var(--accent-primary)]" : ""}>
                        No Folder
                      </span>
                    </DropdownMenuItem>
                    {documentFolders.map((folder) => (
                      <DropdownMenuItem
                        key={folder.id}
                        onClick={() => onMoveToFolder(folder.id)}
                        className="cursor-pointer"
                      >
                        <span className={currentFolderId === folder.id ? "font-semibold text-[var(--accent-primary)]" : ""}>
                          {folder.name}
                        </span>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuSubContent>
                </DropdownMenuSub>

                <DropdownMenuItem onClick={onDuplicate} className="gap-2 cursor-pointer">
                  <Copy size={12} />
                  <span>Duplicate</span>
                </DropdownMenuItem>

                <DropdownMenuItem onClick={onExport} className="gap-2 cursor-pointer">
                  <Download size={12} />
                  <span>Export</span>
                </DropdownMenuItem>

                <DropdownMenuSeparator />

                <DropdownMenuItem
                  onClick={() => onReprocess(document.id)}
                  className="gap-2 cursor-pointer"
                >
                  <RefreshCw size={12} />
                  <span>Reprocess</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onRegenerateEmbeddings(document.id)}
                  className="gap-2 cursor-pointer"
                >
                  <Database size={12} />
                  <span>Regenerate Vectors</span>
                </DropdownMenuItem>

                <DropdownMenuSeparator />

                <DropdownMenuItem
                  onClick={() => setShowDeleteDialog(true)}
                  className="gap-2 text-[var(--accent-error)] focus:bg-red-500/10 focus:text-red-400 cursor-pointer"
                >
                  <Trash size={12} />
                  <span>Delete</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Meta row */}
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-[var(--text-muted)]">
            <div className="flex items-center gap-1.5">
              <Calendar size={11} />
              <span>{relativeTime(document.created_at)}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Layers size={11} />
              <span>{document.page_count ? `${document.page_count} pg` : "1 pg"}</span>
            </div>
            {document.language && (
              <div className="col-span-2 flex items-center gap-1.5">
                <span className="uppercase text-[9px] tracking-wide font-semibold">Lang:</span>
                <span>{document.language.toUpperCase()}</span>
              </div>
            )}
          </div>

          {/* Amber banner: chunking finished but vectorization failed — the
              file is on disk but unsearchable until embeddings are rebuilt. */}
          {embeddingFailed && (
            <div
              className="flex items-center gap-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-400"
              role="alert"
            >
              <AlertTriangle size={13} className="shrink-0" />
              <span
                className="min-w-0 flex-1 truncate"
                title={VECTORIZATION_FAILED_MESSAGE}
              >
                {VECTORIZATION_FAILED_MESSAGE}
              </span>
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={isRegenerating}
                className="shrink-0 inline-flex items-center gap-1 rounded-md border border-amber-500/30 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider cursor-pointer transition-colors hover:bg-amber-500/15 disabled:opacity-50"
              >
                <RefreshCw
                  size={10}
                  className={isRegenerating ? "animate-spin" : undefined}
                />
                {isRegenerating ? "Queuing…" : "Regenerate"}
              </button>
            </div>
          )}

          {/* Live pipeline step — same stage text as the upload queue */}
          {processingStep && (
            <div
              className="flex items-center gap-1.5 text-[11px] text-[var(--accent-primary)]"
              role="status"
              aria-live="polite"
            >
              <span
                className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--accent-primary)] animate-pulse"
                aria-hidden
              />
              <span className="truncate">{processingStep.detail}</span>
            </div>
          )}

          {/* Footer: status badge + quick actions */}
          <div className="flex items-center justify-between border-t border-[var(--border-subtle)] pt-[calc(var(--space-factor,1)*12px)] mt-auto">
            <span
              className={cn(
                "inline-flex items-center text-[9px] px-2 py-0.5 rounded-[var(--radius-pill)] font-bold uppercase tracking-wider",
                STATUS_CLASSES[document.status]
              )}
            >
              {document.status}
            </span>
            {processingStep && (
              <span className="text-[10px] text-[var(--text-muted)] font-medium tabular-nums">
                {processingStep.progress}%
              </span>
            )}

            <div className="flex items-center gap-1">
              <Button
                onClick={onExport}
                variant="ghost"
                size="iconSm"
                className="h-7 w-7 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                title="View / Download"
                aria-label="View or download document"
              >
                <Eye size={12} />
              </Button>
              <Button
                onClick={() => setShowDeleteDialog(true)}
                variant="ghost"
                size="iconSm"
                className="h-7 w-7 text-[var(--text-muted)] hover:text-[var(--accent-error)]"
                title="Delete"
                aria-label="Delete document"
              >
                <Trash size={12} />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Delete dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <Trash size={15} className="text-[var(--accent-error)]" />
              <span>Delete Document?</span>
            </DialogTitle>
            <DialogDescription>
              Permanently remove "{document.original_filename}"? This will delete all text chunks and embedding vectors. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 pt-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowDeleteDialog(false)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleDelete}
              disabled={isDeleting}
              loading={isDeleting}
            >
              {isDeleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default DocumentCard;
