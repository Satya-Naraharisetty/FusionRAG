import React from "react";
import { AlertCircle, FileText, Trash2 } from "lucide-react";
import { Document } from "../../types";
import { DocumentCard } from "./DocumentCard";
import { Skeleton } from "../ui/skeleton";
import { Button } from "../ui/Button";
import { formatBytes, relativeTime, cn } from "../../lib/utils";
import toast from "react-hot-toast";

interface DocumentGridProps {
  filteredAndSortedDocs: Document[];
  isLoading: boolean;
  error: unknown;
  viewMode: "grid" | "list";
  selectedIds: string[];
  handleSelectToggle: (id: string) => void;
  handleSelectAllToggle: (visibleDocs: Document[]) => void;
  onDelete: (id: string) => Promise<unknown>;
  onReprocess: (id: string) => Promise<unknown>;
  onRegenerateEmbeddings: (id: string) => Promise<unknown>;
  folders: { id: string; name: string }[];
  folderMappings: Record<string, string>;
  setFolderMappings: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  handleDragStart: (id: string) => void;
  handleDragOver: (e: React.DragEvent) => void;
  handleDrop: (id: string) => void;
  search: string;
  filter: string;
  selectedFolderId: string | null;
  selectedLanguages: string[];
  dateRange: { start: string; end: string };
}

const STATUS_ROW_CLASSES: Record<Document["status"], string> = {
  pending:    "bg-amber-500/10   text-amber-400   border border-amber-500/20",
  processing: "bg-blue-500/10    text-blue-400    border border-blue-500/20",
  completed:  "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  failed:     "bg-red-500/10     text-red-400     border border-red-500/20",
};

export const DocumentGrid: React.FC<DocumentGridProps> = ({
  filteredAndSortedDocs,
  isLoading,
  error,
  viewMode,
  selectedIds,
  handleSelectToggle,
  handleSelectAllToggle,
  onDelete,
  onReprocess,
  onRegenerateEmbeddings,
  folders,
  folderMappings,
  setFolderMappings,
  handleDragStart,
  handleDragOver,
  handleDrop,
  search,
  filter,
  selectedFolderId,
  selectedLanguages,
  dateRange,
}) => {
  /* ── Loading skeleton ── */
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-[calc(var(--space-factor,1)*12px)]">
        {Array.from({ length: 6 }).map((_, idx) => (
          <div
            key={idx}
            className="h-36 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[var(--radius-xl)] p-[calc(var(--space-factor,1)*16px)] space-y-[calc(var(--space-factor,1)*12px)]"
          >
            <div className="flex items-center gap-3">
              <Skeleton className="h-9 w-9 rounded-[var(--radius-lg)]" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-3 w-3/4" />
                <Skeleton className="h-2 w-1/4" />
              </div>
            </div>
            <Skeleton className="h-2 w-full" />
            <Skeleton className="h-2 w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  /* ── Error ── */
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center text-[var(--accent-error)] select-none">
        <AlertCircle size={22} className="mb-2" />
        <p className="text-xs font-medium">Failed to load documents.</p>
      </div>
    );
  }

  /* ── Empty ── */
  if (filteredAndSortedDocs.length === 0) {
    const hasFilters =
      search || filter !== "all" || selectedFolderId !== null ||
      selectedLanguages.length > 0 || dateRange.start || dateRange.end;

    return (
      <div className="flex flex-col items-center justify-center py-14 px-4 text-center border border-dashed border-[var(--border-default)] rounded-[var(--radius-2xl)] select-none">
        <FileText size={28} className="text-[var(--text-muted)] mb-3" />
        <span className="text-sm font-semibold text-[var(--text-secondary)]">No documents found</span>
        <p className="text-xs text-[var(--text-muted)] max-w-xs mt-1.5 leading-relaxed">
          {hasFilters
            ? "Try adjusting your filters or search terms."
            : "Upload PDF or text documents to start indexing."}
        </p>
      </div>
    );
  }

  /* ── Grid view ── */
  if (viewMode === "grid") {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-[calc(var(--space-factor,1)*12px)]">
        {filteredAndSortedDocs.map((doc) => (
          <DocumentCard
            key={doc.id}
            document={doc}
            onDelete={onDelete}
            onReprocess={onReprocess}
            onRegenerateEmbeddings={onRegenerateEmbeddings}
            isSelected={selectedIds.includes(doc.id)}
            onSelectToggle={() => handleSelectToggle(doc.id)}
            documentFolders={folders}
            currentFolderId={folderMappings[doc.id]}
            onMoveToFolder={(folderId) =>
              setFolderMappings((prev) => {
                const next = { ...prev };
                if (folderId === null) delete next[doc.id];
                else next[doc.id] = folderId;
                return next;
              })
            }
            onDuplicate={() => toast.success(`Duplicated "${doc.original_filename}"`)}
            onExport={() => toast.success(`Exported metadata for "${doc.original_filename}"`)}
            onDragStart={() => handleDragStart(doc.id)}
            onDragOver={handleDragOver}
            onDrop={() => handleDrop(doc.id)}
          />
        ))}
      </div>
    );
  }

  /* ── List view ── */
  return (
    <div className="border border-[var(--border-subtle)] rounded-[var(--radius-xl)] overflow-hidden bg-[var(--bg-secondary)] select-none">
      <table className="doc-table">
        <thead>
          <tr>
            <th className="w-10">
              <input
                type="checkbox"
                checked={
                  filteredAndSortedDocs.length > 0 &&
                  filteredAndSortedDocs.every((d) => selectedIds.includes(d.id))
                }
                onChange={() => handleSelectAllToggle(filteredAndSortedDocs)}
                className="rounded accent-[var(--accent-primary)] cursor-pointer focus:ring-0"
                aria-label="Select all documents"
              />
            </th>
            <th>File Name</th>
            <th className="hidden sm:table-cell">Size</th>
            <th className="hidden sm:table-cell">Uploaded</th>
            <th>Status</th>
            <th className="w-12 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredAndSortedDocs.map((doc) => {
            const isChecked = selectedIds.includes(doc.id);
            return (
              <tr
                key={doc.id}
                className={cn(isChecked && "bg-[var(--bg-tertiary)]/40")}
              >
                <td>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => handleSelectToggle(doc.id)}
                    className="rounded accent-[var(--accent-primary)] cursor-pointer focus:ring-0"
                    aria-label={`Select ${doc.original_filename}`}
                  />
                </td>
                <td className="font-medium text-[var(--text-primary)] max-w-[200px] sm:max-w-xs truncate">
                  <span title={doc.original_filename}>{doc.original_filename}</span>
                </td>
                <td className="hidden sm:table-cell font-mono text-[11px]">
                  {formatBytes(doc.file_size)}
                </td>
                <td className="hidden sm:table-cell font-mono text-[11px]">
                  {relativeTime(doc.created_at)}
                </td>
                <td>
                  <span
                    className={cn(
                      "inline-flex items-center text-[9px] px-2 py-0.5 rounded-[var(--radius-pill)] font-bold uppercase tracking-wider",
                      STATUS_ROW_CLASSES[doc.status]
                    )}
                  >
                    {doc.status}
                  </span>
                </td>
                <td className="text-right">
                  <Button
                    variant="ghost"
                    size="iconSm"
                    onClick={async () => {
                      if (window.confirm(`Delete "${doc.original_filename}"?`)) {
                        await onDelete(doc.id);
                      }
                    }}
                    className="h-7 w-7 text-[var(--text-muted)] hover:text-[var(--accent-error)]"
                    aria-label={`Delete ${doc.original_filename}`}
                  >
                    <Trash2 size={12} />
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default DocumentGrid;
