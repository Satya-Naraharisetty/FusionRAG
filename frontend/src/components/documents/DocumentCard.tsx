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
} from "../ui/dropdown-menu";
import { Button } from "../ui/button";
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

interface DocumentCardProps {
  document: Document;
  onDelete: (id: string) => Promise<unknown>;
  onReprocess: (id: string) => Promise<unknown>;
  onRegenerateEmbeddings: (id: string) => Promise<unknown>;
  // Phase 5 requirements:
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
      // handled in hook
    } finally {
      setIsDeleting(false);
    }
  };

  const statusColors: Record<Document["status"], string> = {
    pending: "bg-amber-950/40 text-amber-400 border-amber-900/30",
    processing: "bg-blue-950/40 text-blue-400 border-blue-900/30",
    completed: "bg-emerald-950/40 text-emerald-400 border-emerald-900/30",
    failed: "bg-red-950/40 text-red-400 border-red-900/30",
  };

  // Thumbnail file type visual stylings
  const fileExt = document.original_filename.split(".").pop()?.toLowerCase() || "";
  const getThumbnailConfig = () => {
    switch (fileExt) {
      case "pdf":
        return { label: "PDF", bg: "bg-red-950/40", border: "border-red-900/30", text: "text-red-400" };
      case "md":
        return { label: "MD", bg: "bg-fuchsia-950/40", border: "border-fuchsia-900/30", text: "text-fuchsia-400" };
      case "docx":
      case "doc":
        return { label: "DOCX", bg: "bg-blue-950/40", border: "border-blue-900/30", text: "text-blue-400" };
      default:
        return { label: "TXT", bg: "bg-zinc-900/60", border: "border-zinc-800", text: "text-zinc-400" };
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
          "group bg-zinc-900/10 backdrop-blur-md border overflow-hidden hover:border-zinc-800 hover:bg-zinc-900/20 hover:-translate-y-0.5 hover:shadow-[0_8px_30px_rgba(0,0,0,0.35)] transition-all duration-300",
          isSelected ? "border-violet-600/80 bg-violet-950/5" : "border-zinc-900/80"
        )}
      >
        <CardContent className="p-4 flex flex-col justify-between h-full gap-4">
          {/* Header Row */}
          <div className="flex items-start justify-between gap-1">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              {/* Drag Handle & Checkbox */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <div className="cursor-grab active:cursor-grabbing text-zinc-650 hover:text-zinc-400 p-0.5" title="Drag to reorder">
                  <GripVertical size={14} />
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectToggle();
                  }}
                  className="text-zinc-500 hover:text-violet-400 cursor-pointer p-0.5"
                  aria-label={isSelected ? "Deselect file" : "Select file"}
                >
                  {isSelected ? (
                    <CheckSquare size={15} className="text-violet-500 fill-violet-950/20" />
                  ) : (
                    <Square size={15} />
                  )}
                </button>
              </div>

              {/* PDF/Text Thumbnail preview */}
              <div className={cn(
                "flex h-9 w-9 flex-col items-center justify-center rounded-lg border font-mono font-bold text-[9px] flex-shrink-0 transition-all duration-300 shadow-sm",
                thumb.bg,
                thumb.border,
                thumb.text
              )}>
                <FileText size={12} className="mb-0.5" />
                <span>{thumb.label}</span>
              </div>

              <div className="min-w-0 flex-1">
                <h4
                  className="text-xs font-bold text-zinc-200 truncate"
                  title={document.original_filename}
                >
                  {document.original_filename}
                </h4>
                <p className="text-[10px] text-zinc-500 font-mono">
                  {formatBytes(document.file_size)}
                </p>
              </div>
            </div>

            {/* Dropdown Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900 cursor-pointer"
                  aria-label="Document options"
                >
                  <MoreVertical size={14} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="w-52 bg-zinc-950 border-zinc-800 text-zinc-300"
              >
                {/* Move to Folder submenu */}
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
                      <span className={!currentFolderId ? "font-bold text-violet-400" : ""}>
                        No Folder
                      </span>
                    </DropdownMenuItem>
                    {documentFolders.map((folder) => (
                      <DropdownMenuItem
                        key={folder.id}
                        onClick={() => onMoveToFolder(folder.id)}
                        className="text-xs cursor-pointer focus:bg-zinc-900"
                      >
                        <span className={currentFolderId === folder.id ? "font-bold text-violet-400" : ""}>
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

          {/* Details Grid */}
          <div className="grid grid-cols-2 gap-2 text-[10px] text-zinc-400">
            <div className="flex items-center gap-1.5">
              <Calendar size={12} className="text-zinc-650" />
              <span>{relativeTime(document.created_at)}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Layers size={12} className="text-zinc-650" />
              <span>
                {document.page_count ? `${document.page_count} pages` : "1 page"}
              </span>
            </div>
            {document.language && (
              <div className="flex items-center gap-1.5 col-span-2">
                <span className="font-semibold text-zinc-500 uppercase text-[9px] tracking-wide">
                  Lang:
                </span>
                <span>{document.language.toUpperCase()}</span>
              </div>
            )}
          </div>

          {/* Badges / Status Row */}
          <div className="flex items-center justify-between border-t border-zinc-900/60 pt-3">
            <Badge
              variant="outline"
              className={cn(
                "text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider",
                statusColors[document.status]
              )}
            >
              {document.status}
            </Badge>

            {document.status === "processing" && (
              <div className="flex items-center gap-1.5 text-blue-400">
                {/* SVG inline progress ring */}
                <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span className="text-[9px] font-bold uppercase tracking-wider animate-pulse">
                  Processing...
                </span>
              </div>
            )}

            {document.status === "failed" && document.failure_reason && (
              <span
                className="text-[9px] text-red-400 max-w-[150px] truncate"
                title={document.failure_reason}
              >
                {document.failure_reason}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Delete Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-200 sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2">
              <Trash size={18} className="text-red-500" />
              <span>Delete Document?</span>
            </DialogTitle>
            <DialogDescription className="text-zinc-400 text-xs mt-2">
              Are you sure you want to delete this document? Doing so will permanently wipe its
              file metadata, text chunks, and embedding vectors from the database.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4 flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
              className="bg-transparent border-zinc-800 text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100 text-xs"
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              className="bg-red-650 hover:bg-red-750 text-white text-xs"
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
