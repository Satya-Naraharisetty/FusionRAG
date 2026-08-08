import React, { useState } from "react";
import {
  FileText,
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
} from "lucide-react";
import { Document } from "../../types";
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
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
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

export const DocumentCard: React.FC<DocumentCardProps> = ({
  document,
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
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(document.id);
      setShowDeleteDialog(false);
    } catch (_e) {
      // Handled in hook
    } finally {
      setIsDeleting(false);
    }
  };

  const statusColors: Record<Document["status"], string> = {
    pending: "bg-amber-100 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-900/30",
    processing: "bg-blue-100 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-900/30",
    completed: "bg-emerald-100 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-900/30",
    failed: "bg-red-100 dark:bg-red-950/20 text-red-650 dark:text-red-400 border-red-200 dark:border-red-900/30",
  };

  const fileExt = document.original_filename.split(".").pop()?.toLowerCase() || "";
  
  const getThumbnailConfig = () => {
    switch (fileExt) {
      case "pdf":
        return { label: "PDF", bg: "bg-red-50 dark:bg-red-950/30", border: "border-red-200 dark:border-red-900/20", text: "text-red-600 dark:text-red-400" };
      case "md":
        return { label: "MD", bg: "bg-fuchsia-50 dark:bg-fuchsia-950/30", border: "border-fuchsia-200 dark:border-fuchsia-900/20", text: "text-fuchsia-600 dark:text-fuchsia-400" };
      case "docx":
      case "doc":
        return { label: "DOCX", bg: "bg-blue-50 dark:bg-blue-950/30", border: "border-blue-200 dark:border-blue-900/20", text: "text-blue-600 dark:text-blue-400" };
      default:
        return { label: "TXT", bg: "bg-zinc-55 dark:bg-zinc-900/60", border: "border-zinc-200 dark:border-zinc-800", text: "text-zinc-550 dark:text-zinc-400" };
    }
  };

  const thumb = getThumbnailConfig();

  return (
    <>
      <Card
        draggable="true"
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDrop={onDrop}
        className={cn(
          "group flex flex-col bg-white dark:bg-[#1e1e1e] border rounded-2xl transition-all duration-300 overflow-hidden select-none hover:shadow-md",
          isSelected
            ? "border-zinc-900 dark:border-zinc-100 ring-1 ring-zinc-900 dark:ring-zinc-100 bg-zinc-50/50 dark:bg-zinc-800/10"
            : "border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700"
        )}
      >
        <CardContent className="p-5 flex flex-col justify-between h-full gap-4.5">
          {/* Header row: Checkbox, file info, drag handles */}
          <div className="flex items-start justify-between gap-1.5">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {/* Reorder drag handle */}
                <div className="cursor-grab active:cursor-grabbing text-zinc-400 dark:text-zinc-600 hover:text-zinc-600 dark:hover:text-zinc-300 p-0.5" title="Drag to reorder">
                  <GripVertical size={14} />
                </div>
                {/* Select checkbox */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectToggle();
                  }}
                  className="text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200 cursor-pointer p-0.5"
                  aria-label={isSelected ? "Deselect document" : "Select document"}
                >
                  {isSelected ? (
                    <CheckSquare size={15} className="text-zinc-800 dark:text-zinc-100 fill-zinc-800/10 dark:fill-zinc-100/10" />
                  ) : (
                    <Square size={15} />
                  )}
                </button>
              </div>

              {/* Styled Document Type Icon */}
              <div className={cn(
                "flex h-10 w-10 flex-col items-center justify-center rounded-xl border font-mono font-bold text-[9px] flex-shrink-0 shadow-xs",
                thumb.bg,
                thumb.border,
                thumb.text
              )}>
                <FileText size={14} className="mb-0.5" />
                <span>{thumb.label}</span>
              </div>

              {/* Doc Title and Size */}
              <div className="min-w-0 flex-1">
                <h4
                  className="text-xs font-bold text-zinc-800 dark:text-zinc-150 truncate leading-snug"
                  title={document.original_filename}
                >
                  {document.original_filename}
                </h4>
                <p className="text-[10px] text-zinc-400 dark:text-zinc-550 font-medium">
                  {formatBytes(document.file_size)}
                </p>
              </div>
            </div>

            {/* Context dropdown option menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-zinc-400 dark:text-zinc-550 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800/50 cursor-pointer"
                  aria-label="Document options"
                >
                  <MoreVertical size={14} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="w-52 bg-zinc-950 border-zinc-800 text-zinc-300"
              >
                {/* Move to folder */}
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger className="gap-2 text-xs cursor-pointer focus:bg-zinc-900">
                    <FolderOpen size={12} />
                    <span>Move to Folder</span>
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent className="bg-zinc-950 border-zinc-850 text-zinc-300 w-44">
                    <DropdownMenuItem
                      onClick={() => onMoveToFolder(null)}
                      className="text-xs cursor-pointer focus:bg-zinc-900"
                    >
                      <span className={!currentFolderId ? "font-bold text-zinc-200" : ""}>
                        No Folder
                      </span>
                    </DropdownMenuItem>
                    {documentFolders.map((folder) => (
                      <DropdownMenuItem
                        key={folder.id}
                        onClick={() => onMoveToFolder(folder.id)}
                        className="text-xs cursor-pointer focus:bg-zinc-900"
                      >
                        <span className={currentFolderId === folder.id ? "font-bold text-zinc-200" : ""}>
                          {folder.name}
                        </span>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuSubContent>
                </DropdownMenuSub>

                <DropdownMenuItem
                  onClick={onDuplicate}
                  className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-xs"
                >
                  <Copy size={12} />
                  <span>Duplicate</span>
                </DropdownMenuItem>

                <DropdownMenuItem
                  onClick={onExport}
                  className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-xs"
                >
                  <Download size={12} />
                  <span>Export</span>
                </DropdownMenuItem>

                <DropdownMenuSeparator className="bg-zinc-850" />

                <DropdownMenuItem
                  onClick={() => onReprocess(document.id)}
                  className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-xs"
                >
                  <RefreshCw size={12} />
                  <span>Reprocess File</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onRegenerateEmbeddings(document.id)}
                  className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-xs"
                >
                  <Database size={12} />
                  <span>Regenerate Vectors</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => setShowDeleteDialog(true)}
                  className="gap-2 text-red-400 focus:bg-red-950/20 focus:text-red-300 cursor-pointer text-xs"
                >
                  <Trash size={12} />
                  <span>Delete File</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Details Row: Calendar, page count */}
          <div className="grid grid-cols-2 gap-2 text-[10px] text-zinc-550 dark:text-zinc-450">
            <div className="flex items-center gap-1.5">
              <Calendar size={12} className="text-zinc-400 dark:text-zinc-600" />
              <span>{relativeTime(document.created_at)}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Layers size={12} className="text-zinc-400 dark:text-zinc-600" />
              <span>
                {document.page_count ? `${document.page_count} pages` : "1 page"}
              </span>
            </div>
            {document.language && (
              <div className="flex items-center gap-1.5 col-span-2">
                <span className="font-semibold text-zinc-400 dark:text-zinc-500 uppercase text-[9px] tracking-wide">
                  Language:
                </span>
                <span>{document.language.toUpperCase()}</span>
              </div>
            )}
          </div>

          {/* Bottom Row: Status pill and View/Delete quick-action buttons */}
          <div className="flex items-center justify-between border-t border-zinc-100 dark:border-zinc-800/80 pt-3.5 mt-0.5">
            <Badge
              variant="outline"
              className={cn(
                "text-[9px] px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider",
                statusColors[document.status]
              )}
            >
              {document.status}
            </Badge>

            {/* Quick Actions (View / Delete) */}
            <div className="flex items-center gap-1.5">
              {/* View/Export download button */}
              <Button
                onClick={onExport}
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-200 rounded-md"
                title="View / Download"
              >
                <Eye size={13} />
              </Button>
              {/* Delete button */}
              <Button
                onClick={() => setShowDeleteDialog(true)}
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-zinc-500 hover:text-red-500 dark:hover:text-red-400 rounded-md"
                title="Delete"
              >
                <Trash size={13} />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Delete Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="bg-[#171717] border-zinc-800 text-zinc-200 sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-zinc-150 flex items-center gap-2">
              <Trash size={18} className="text-red-550" />
              <span>Delete Document?</span>
            </DialogTitle>
            <DialogDescription className="text-zinc-450 text-xs mt-2 leading-relaxed">
              Are you sure you want to delete this document? Doing so will permanently wipe its
              file metadata, text chunks, and embedding vectors from the database.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4 flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
              className="bg-transparent border-zinc-800 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 text-xs"
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              className="bg-red-650 hover:bg-red-750 text-white text-xs font-semibold"
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
export default DocumentCard;
