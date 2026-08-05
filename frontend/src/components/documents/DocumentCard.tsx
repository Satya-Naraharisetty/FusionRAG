import React, { useState } from "react";
import {
  FileText,
  MoreVertical,
  RefreshCw,
  Trash,
  Database,
  Calendar,
  Layers,
} from "lucide-react";
import { Document } from "../../types";
import { formatBytes, relativeTime, cn } from "../../lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
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
}

export const DocumentCard: React.FC<DocumentCardProps> = ({
  document,
  onDelete,
  onReprocess,
  onRegenerateEmbeddings,
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

  return (
    <>
      <Card className="bg-zinc-950/40 border-zinc-900 overflow-hidden shadow-sm hover:border-zinc-800 transition-all duration-200">
        <CardContent className="p-4 flex flex-col justify-between h-full gap-4">
          {/* Header Row */}
          <div className="flex items-start justify-between gap-2.5">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-400 flex-shrink-0">
                <FileText size={16} />
              </div>
              <div className="min-w-0">
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
                className="w-48 bg-zinc-950 border-zinc-800 text-zinc-300"
              >
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
              className="bg-red-600 hover:bg-red-700 text-white text-xs"
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
