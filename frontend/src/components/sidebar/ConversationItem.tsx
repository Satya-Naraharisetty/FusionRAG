import React, { useState, useRef, useEffect } from "react";
import { MessageSquare, Trash2, Pin, Archive } from "lucide-react";
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
} from "../ui/Modal";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { Folder, Tag } from "../../hooks/useLocalConversationMetadata";

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
  isPinned: boolean;
  onTogglePin: () => void;
  folders: Folder[];
  onMoveToFolder: (folderId: string | null) => void;
  currentFolderId?: string;
  tags: Tag[];
  onAddTag: (tag: Tag) => void;
  onRemoveTag: (name: string) => void;
  isHighlighted?: boolean;
}

export const ConversationItem: React.FC<ConversationItemProps> = ({
  conversation,
  isActive,
  onSelect,
  onRename,
  onDelete,
  isPinned,
  onTogglePin,
  folders,
  onMoveToFolder,
  currentFolderId,
  tags,
  onAddTag,
  onRemoveTag,
  isHighlighted = false,
}) => {
  const [isEditing, setIsEditing]         = useState(false);
  const [editTitle, setEditTitle]         = useState(conversation.title);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting]       = useState(false);

  // Swipe gesture
  const [swipeOffset, setSwipeOffset]   = useState(0);
  const touchStart                      = useRef<{ x: number; y: number } | null>(null);
  const isSwiping                       = useRef(false);

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
    } catch {
      setEditTitle(conversation.title);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter")  handleSaveRename();
    if (e.key === "Escape") { setIsEditing(false); setEditTitle(conversation.title); }
  };

  const handleDeleteConfirm = async () => {
    setIsDeleting(true);
    try {
      await onDelete(conversation.id);
      setShowDeleteDialog(false);
    } finally {
      setIsDeleting(false);
    }
  };

  // Drag & drop
  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData("text/plain", conversation.id);
    e.dataTransfer.effectAllowed = "move";
  };

  // Touch swipe
  const handleTouchStart = (e: React.TouchEvent) => {
    const t = e.touches[0];
    touchStart.current = { x: t.clientX, y: t.clientY };
    isSwiping.current = false;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStart.current) return;
    const t = e.touches[0];
    const dx = t.clientX - touchStart.current.x;
    const dy = t.clientY - touchStart.current.y;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 10) {
      isSwiping.current = true;
      if (dx < 0) setSwipeOffset(Math.max(-130, dx));
      else        setSwipeOffset(Math.min(0, dx));
    }
  };

  const handleTouchEnd = () => {
    touchStart.current = null;
    if (!isSwiping.current) return;
    setSwipeOffset(swipeOffset < -50 ? -130 : 0);
  };

  return (
    <>
      <div
        draggable="true"
        onDragStart={handleDragStart}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        className={cn(
          "relative overflow-hidden group select-none rounded-[var(--radius-md)] transition-all duration-150",
          isHighlighted && "bg-[var(--bg-tertiary)]"
        )}
      >
        {/* Swipe quick-actions drawer */}
        <div className="absolute right-0 top-0 bottom-0 flex items-center bg-[var(--bg-secondary)] border-l border-[var(--border-subtle)]">
          <button
            onClick={(e) => { e.stopPropagation(); onTogglePin(); setSwipeOffset(0); }}
            className="flex flex-col items-center justify-center h-full w-[42px] bg-amber-500/10 text-amber-500 hover:bg-amber-500/20 cursor-pointer transition-colors"
            title="Pin"
            aria-label="Pin conversation"
          >
            <Pin size={12} className={isPinned ? "fill-amber-500" : ""} />
            <span className="text-[8px] mt-0.5">Pin</span>
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setSwipeOffset(0); }}
            className="flex flex-col items-center justify-center h-full w-[42px] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20 cursor-pointer transition-colors"
            title="Archive"
            aria-label="Archive conversation"
          >
            <Archive size={12} />
            <span className="text-[8px] mt-0.5">Arch</span>
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setShowDeleteDialog(true); setSwipeOffset(0); }}
            className="flex flex-col items-center justify-center h-full w-[46px] bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer transition-colors"
            title="Delete"
            aria-label="Delete conversation"
          >
            <Trash2 size={12} />
            <span className="text-[8px] mt-0.5">Delete</span>
          </button>
        </div>

        {/* Main row */}
        <div
          onClick={isEditing ? undefined : onSelect}
          style={{ transform: `translateX(${swipeOffset}px)` }}
          className={cn(
            "relative flex items-center justify-between gap-2 px-2.5 py-2 rounded-[var(--radius-md)] text-xs cursor-pointer transition-colors",
            isActive
              ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)] font-medium"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]/60"
          )}
          role="button"
          aria-current={isActive ? "page" : undefined}
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {/* Icon */}
            <div className="relative flex-shrink-0">
              <MessageSquare
                size={13}
                className={cn(
                  "transition-colors",
                  isActive ? "text-[var(--accent-primary)]" : "text-[var(--text-muted)] group-hover:text-[var(--text-secondary)]"
                )}
              />
              {isPinned && (
                <div className="absolute -top-1 -right-1 h-2.5 w-2.5 flex items-center justify-center rounded-full bg-amber-500 border border-[var(--bg-secondary)]">
                  <Pin size={6} className="fill-white text-white" />
                </div>
              )}
            </div>

            {/* Title / Edit input */}
            <div className="flex-1 min-w-0">
              {isEditing ? (
                <Input
                  ref={inputRef}
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={handleSaveRename}
                  onKeyDown={handleKeyDown}
                  className="h-6 w-full text-xs px-1.5 py-0.5 rounded-[var(--radius-sm)]"
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className="truncate block leading-snug">{conversation.title}</span>
              )}

              {/* Inline tag dots */}
              {tags.length > 0 && !isEditing && (
                <div className="flex gap-1 mt-0.5">
                  {tags.map((t) => (
                    <span
                      key={t.name}
                      className={cn("inline-block h-1.5 w-1.5 rounded-full", t.color || "bg-[var(--accent-primary)]")}
                      title={t.name}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Context menu — shows on row hover */}
          {!isEditing && (
            <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-150">
              <ConversationMenu
                onRename={() => setIsEditing(true)}
                onDelete={() => setShowDeleteDialog(true)}
                isPinned={isPinned}
                onTogglePin={onTogglePin}
                folders={folders}
                onMoveToFolder={onMoveToFolder}
                currentFolderId={currentFolderId}
                tags={tags}
                onAddTag={onAddTag}
                onRemoveTag={onRemoveTag}
              />
            </div>
          )}
        </div>
      </div>

      {/* Delete confirmation dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm">
              <Trash2 size={15} className="text-[var(--accent-error)]" />
              <span>Delete Conversation?</span>
            </DialogTitle>
            <DialogDescription>
              Permanently delete "{conversation.title}" and all its message history? This cannot be undone.
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
              onClick={handleDeleteConfirm}
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
