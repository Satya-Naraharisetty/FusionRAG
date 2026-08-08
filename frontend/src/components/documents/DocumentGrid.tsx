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
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, idx) => (
          <div key={idx} className="h-40 bg-zinc-50 dark:bg-zinc-900/40 border border-zinc-200 dark:border-zinc-800 rounded-2xl p-4.5 space-y-4">
            <div className="flex items-center gap-3">
              <Skeleton className="h-9 w-9 rounded-xl bg-zinc-200 dark:bg-zinc-800 animate-pulse" />
              <div className="space-y-2 flex-1 animate-pulse">
                <Skeleton className="h-3 w-3/4 bg-zinc-200 dark:bg-zinc-850" />
                <Skeleton className="h-2 w-1/4 bg-zinc-200 dark:bg-zinc-850" />
              </div>
            </div>
            <div className="space-y-2 animate-pulse">
              <Skeleton className="h-2 w-full bg-zinc-200 dark:bg-zinc-850" />
              <Skeleton className="h-2 w-2/3 bg-zinc-200 dark:bg-zinc-850" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center text-red-500 select-none">
        <AlertCircle size={24} className="mb-2" />
        <p className="text-xs font-semibold">Failed to fetch document library.</p>
      </div>
    );
  }

  if (filteredAndSortedDocs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center border border-zinc-200 dark:border-zinc-800 border-dashed rounded-2xl select-none">
        <FileText size={32} className="text-zinc-400 dark:text-zinc-700 mb-2" />
        <span className="text-xs font-bold text-zinc-650 dark:text-zinc-400">No documents found</span>
        <p className="text-[10px] text-zinc-500 dark:text-zinc-550 max-w-xs mt-1 leading-relaxed">
          {search || filter !== "all" || selectedFolderId !== null || selectedLanguages.length > 0 || dateRange.start || dateRange.end
            ? "Try adjusting your filters or search terms."
            : "Upload PDF or text documents to start indexing."}
        </p>
      </div>
    );
  }

  if (viewMode === "grid") {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
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
                if (folderId === null) {
                  delete next[doc.id];
                } else {
                  next[doc.id] = folderId;
                }
                return next;
              })
            }
            onDuplicate={() => {
              toast.success(`Duplicated document "${doc.original_filename}"`);
            }}
            onExport={() => {
              toast.success(`Exported metadata for "${doc.original_filename}"`);
            }}
            onDragStart={() => handleDragStart(doc.id)}
            onDragOver={handleDragOver}
            onDrop={() => handleDrop(doc.id)}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="border border-zinc-200 dark:border-zinc-800 rounded-2xl overflow-hidden bg-white dark:bg-[#1e1e1e] shadow-xs select-none">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/30 text-[10px] font-bold text-zinc-500 dark:text-zinc-450 uppercase tracking-widest">
            <th className="p-3.5 w-10">
              <input
                type="checkbox"
                checked={
                  filteredAndSortedDocs.length > 0 &&
                  filteredAndSortedDocs.every((d) => selectedIds.includes(d.id))
                }
                onChange={() => handleSelectAllToggle(filteredAndSortedDocs)}
                className="rounded accent-zinc-900 dark:accent-zinc-100 cursor-pointer focus:ring-0"
              />
            </th>
            <th className="p-3.5 text-xs">File Name</th>
            <th className="p-3.5 text-xs hidden sm:table-cell">Size</th>
            <th className="p-3.5 text-xs hidden sm:table-cell">Uploaded</th>
            <th className="p-3.5 text-xs">Status</th>
            <th className="p-3.5 text-xs w-12 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 text-xs text-zinc-700 dark:text-zinc-300">
          {filteredAndSortedDocs.map((doc) => {
            const isChecked = selectedIds.includes(doc.id);
            return (
              <tr
                key={doc.id}
                className={`hover:bg-zinc-50 dark:hover:bg-zinc-850/40 transition-colors ${
                  isChecked ? "bg-zinc-50 dark:bg-zinc-800/10" : ""
                }`}
              >
                <td className="p-3.5">
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => handleSelectToggle(doc.id)}
                    className="rounded accent-zinc-900 dark:accent-zinc-100 cursor-pointer focus:ring-0"
                  />
                </td>
                <td className="p-3.5 font-semibold text-zinc-900 dark:text-zinc-150 max-w-[200px] sm:max-w-xs truncate">
                  <span title={doc.original_filename}>{doc.original_filename}</span>
                </td>
                <td className="p-3.5 hidden sm:table-cell text-zinc-500 dark:text-zinc-450 font-medium font-mono text-[10px]">
                  {formatBytes(doc.file_size)}
                </td>
                <td className="p-3.5 hidden sm:table-cell text-zinc-500 dark:text-zinc-450 font-medium font-mono text-[10px]">
                  {relativeTime(doc.created_at)}
                </td>
                <td className="p-3.5">
                  <span
                    className={cn(
                      "text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider border",
                      doc.status === "completed" && "bg-emerald-100 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400 border-emerald-250 dark:border-emerald-900/30",
                      doc.status === "processing" && "bg-blue-100 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 border-blue-250 dark:border-blue-900/30",
                      doc.status === "failed" && "bg-red-100 dark:bg-red-950/20 text-red-650 dark:text-red-400 border-red-250 dark:border-red-900/30",
                      doc.status === "pending" && "bg-amber-100 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400 border-amber-250 dark:border-amber-900/30"
                    )}
                  >
                    {doc.status}
                  </span>
                </td>
                <td className="p-3.5 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={async () => {
                      if (window.confirm(`Delete document "${doc.original_filename}"?`)) {
                        await onDelete(doc.id);
                      }
                    }}
                    className="h-7 w-7 text-zinc-400 dark:text-zinc-650 hover:text-red-500 dark:hover:text-red-400 cursor-pointer rounded-md"
                  >
                    <Trash2 size={13} />
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
