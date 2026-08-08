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
  // Local metadata props
  isPinned: boolean;
  onTogglePin: () => void;
  folders: Folder[];
  onMoveToFolder: (folderId: string | null) => void;
  currentFolderId?: string;
  tags: Tag[];
  onAddTag: (tag: Tag) => void;
  onRemoveTag: (name: string) => void;
  isHighlighted?: boolean; // for keyboard navigation styling
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
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(conversation.title);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Swipe gesture state
  const [swipeOffset, setSwipeOffset] = useState(0);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const isSwiping = useRef(false);

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

  // Drag & drop handlers
  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData("text/plain", conversation.id);
    e.dataTransfer.effectAllowed = "move";
  };

  // Touch Swipe handlers
  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];
    touchStart.current = { x: touch.clientX, y: touch.clientY };
    isSwiping.current = false;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStart.current) return;
    const touch = e.touches[0];
    const diffX = touch.clientX - touchStart.current.x;
    const diffY = touch.clientY - touchStart.current.y;

    // Detect horizontal swipe vs vertical scroll
    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 10) {
      isSwiping.current = true;
      // We want swipe left (diffX < 0) to expose right-side options
      if (diffX < 0) {
        setSwipeOffset(Math.max(-130, diffX));
      } else {
        setSwipeOffset(Math.min(0, diffX));
      }
    }
  };

  const handleTouchEnd = () => {
    touchStart.current = null;
    if (!isSwiping.current) return;

    // Snap threshold: if swiped more than 50px, snap open, otherwise snap shut
    if (swipeOffset < -50) {
      setSwipeOffset(-130); // show quick action options
    } else {
      setSwipeOffset(0);
    }
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
          "relative overflow-hidden group select-none rounded-lg border border-transparent transition-all duration-200",
          isHighlighted && "bg-zinc-800/40 border-zinc-700/50 shadow-sm"
        )}
      >
        {/* Swipe Quick Actions Drawer */}
        <div className="absolute right-0 top-0 bottom-0 flex items-center bg-zinc-900 border-l border-zinc-800">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onTogglePin();
              setSwipeOffset(0);
            }}
            className="flex flex-col items-center justify-center h-full w-[42px] bg-amber-950/20 text-amber-500 hover:bg-amber-950/40 cursor-pointer"
            title="Pin"
          >
            <Pin size={13} className={isPinned ? "fill-amber-500" : ""} />
            <span className="text-[8px] mt-0.5">Pin</span>
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSwipeOffset(0);
              // Archive action
            }}
            className="flex flex-col items-center justify-center h-full w-[42px] bg-violet-950/20 text-violet-400 hover:bg-violet-950/40 cursor-pointer"
            title="Archive"
          >
            <Archive size={13} />
            <span className="text-[8px] mt-0.5">Arch</span>
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowDeleteDialog(true);
              setSwipeOffset(0);
            }}
            className="flex flex-col items-center justify-center h-full w-[46px] bg-red-950/20 text-red-500 hover:bg-red-950/40 cursor-pointer"
            title="Delete"
          >
            <Trash2 size={13} />
            <span className="text-[8px] mt-0.5">Delete</span>
          </button>
        </div>

        {/* Conversation item main bubble */}
        <div
          onClick={isEditing ? undefined : onSelect}
          style={{ transform: `translateX(${swipeOffset}px)` }}
          className={cn(
            "relative flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg text-xs font-semibold cursor-pointer transition-all duration-300 border-l-2 bg-transparent",
            isActive
              ? "bg-violet-950/25 text-zinc-100 shadow-sm border-violet-900/30 border-l-violet-500"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40 border-transparent hover:border-l-zinc-800"
          )}
          role="button"
          aria-current={isActive ? "page" : undefined}
        >
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <div className="relative flex-shrink-0">
              <MessageSquare
                size={14}
                className={cn(
                  "transition-colors duration-300",
                  isActive ? "text-violet-400" : "text-zinc-500 group-hover:text-zinc-400"
                )}
              />
              {isPinned && (
                <div className="absolute -top-1.5 -right-1.5 h-3 w-3 flex items-center justify-center rounded-full bg-amber-500 text-zinc-950 border border-zinc-950 scale-75">
                  <Pin size={8} className="fill-current" />
                </div>
              )}
            </div>

            <div className="flex-1 min-w-0 flex flex-col gap-0.5">
              {isEditing ? (
                <Input
                  ref={inputRef}
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={handleSaveRename}
                  onKeyDown={handleKeyDown}
                  className="h-6 w-full bg-zinc-900 border-zinc-800 text-zinc-200 text-xs px-1.5 py-0.5 rounded-md focus-visible:ring-1 focus-visible:ring-violet-600"
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className="truncate pr-4 transition-colors duration-300">
                  {conversation.title}
                </span>
              )}

              {/* Tags inline list */}
              {tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {tags.map((t) => (
                    <span
                      key={t.name}
                      className={cn(
                        "inline-block h-1.5 w-1.5 rounded-full",
                        t.color || "bg-violet-500"
                      )}
                      title={t.name}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {!isEditing && (
            <div className="absolute right-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
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

      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-200 sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-zinc-100 flex items-center gap-2">
              <Trash2 size={18} className="text-red-500" />
              <span>Delete Conversation?</span>
            </DialogTitle>
            <DialogDescription className="text-zinc-400 text-xs mt-2">
              Are you sure you want to delete this conversation? This will permanently remove all
              message history for "{conversation.title}". This action cannot be undone.
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
