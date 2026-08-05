import React, { useState, useRef, useEffect } from "react";
import { MessageSquare, Trash2 } from "lucide-react";
import { Conversation } from "../../types";
import { ConversationMenu } from "./ConversationMenu";
import { cn } from "../../lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
}

export const ConversationItem: React.FC<ConversationItemProps> = ({
  conversation,
  isActive,
  onSelect,
  onRename,
  onDelete,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(conversation.title);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSaveRename = async () => {
    const trimmed = editTitle.trim();
    if (!trimmed || trimmed === conversation.title) {
      setIsEditing(false);
      setEditTitle(conversation.title);
      return;
    }

    setIsEditing(false);
    try {
      await onRename(conversation.id, trimmed);
    } catch (_e) {
      // Revert title on error
      setEditTitle(conversation.title);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSaveRename();
    } else if (e.key === "Escape") {
      setIsEditing(false);
      setEditTitle(conversation.title);
    }
  };

  const handleDeleteConfirm = async () => {
    setIsDeleting(true);
    try {
      await onDelete(conversation.id);
      setShowDeleteDialog(false);
    } catch (_e) {
      // Handled in mutation
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <div
        onClick={isEditing ? undefined : onSelect}
        className={cn(
          "group relative flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg text-xs font-medium cursor-pointer transition-all duration-200 select-none",
          isActive
            ? "bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700/50"
            : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50 border border-transparent"
        )}
        role="button"
        aria-current={isActive ? "page" : undefined}
      >
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <MessageSquare
            size={14}
            className={cn("flex-shrink-0", isActive ? "text-violet-500" : "text-zinc-500")}
          />
          {isEditing ? (
            <Input
              ref={inputRef}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onBlur={handleSaveRename}
              onKeyDown={handleKeyDown}
              className="h-6 w-full bg-zinc-900 border-zinc-700 text-zinc-200 text-xs px-1.5 py-0.5 rounded focus-visible:ring-1 focus-visible:ring-violet-600"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className="truncate pr-4">{conversation.title}</span>
          )}
        </div>

        {!isEditing && (
          <div className="absolute right-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
            <ConversationMenu
              onRename={() => setIsEditing(true)}
              onDelete={() => setShowDeleteDialog(true)}
            />
          </div>
        )}
      </div>

      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-200 sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2">
              <Trash2 size={18} className="text-red-500" />
              <span>Delete Conversation?</span>
            </DialogTitle>
            <DialogDescription className="text-zinc-400 text-xs mt-2">
              Are you sure you want to delete this conversation? This will permanently remove all message history for "{conversation.title}". This action cannot be undone.
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
              onClick={handleDeleteConfirm}
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
