import React from "react";
import {
  MoreHorizontal,
  Pencil,
  Trash,
  FileDown,
  Archive,
  Copy,
  Pin,
  FolderOpen,
  Tag as TagIcon,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from "../ui/Dropdown";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { Folder, Tag } from "../../hooks/useLocalConversationMetadata";

interface ConversationMenuProps {
  onRename: () => void;
  onDelete: () => void;
  isPinned: boolean;
  onTogglePin: () => void;
  folders: Folder[];
  onMoveToFolder: (folderId: string | null) => void;
  currentFolderId?: string;
  tags: Tag[];
  onAddTag: (tag: Tag) => void;
  onRemoveTag: (name: string) => void;
}

const COLOR_OPTIONS = [
  { name: "Violet",  color: "bg-violet-500" },
  { name: "Emerald", color: "bg-emerald-500" },
  { name: "Rose",    color: "bg-rose-500" },
  { name: "Amber",   color: "bg-amber-500" },
  { name: "Blue",    color: "bg-blue-500" },
];

export const ConversationMenu: React.FC<ConversationMenuProps> = ({
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
}) => {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-sm)] hover:bg-[var(--bg-elevated)] text-[var(--text-muted)] hover:text-[var(--text-primary)] focus:outline-none cursor-pointer transition-colors"
          aria-label="More actions"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal size={14} />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-52">
        {/* Pin / Unpin */}
        <DropdownMenuItem
          onClick={(e) => { e.stopPropagation(); onTogglePin(); }}
          className="gap-2 cursor-pointer"
        >
          <Pin size={13} className={isPinned ? "fill-[var(--accent-primary)] text-[var(--accent-primary)]" : ""} />
          <span>{isPinned ? "Unpin" : "Pin"}</span>
        </DropdownMenuItem>

        {/* Direct Remove from Folder ONLY if currently foldered */}
        {Boolean(currentFolderId) && (
          <DropdownMenuItem
            onClick={(e) => { e.stopPropagation(); onMoveToFolder(null); }}
            className="gap-2 cursor-pointer text-amber-500 dark:text-amber-400"
          >
            <FolderOpen size={13} />
            <span>Remove from Folder</span>
          </DropdownMenuItem>
        )}

        {/* Move to Folder */}
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="gap-2 cursor-pointer">
            <FolderOpen size={13} />
            <span>Move to Project / Folder</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="w-52 max-h-60 overflow-y-auto scrollbar-thin">
            <DropdownMenuItem
              onClick={(e) => { e.stopPropagation(); onMoveToFolder(null); }}
              className="cursor-pointer"
            >
              <span className={!currentFolderId ? "font-semibold text-[var(--accent-primary)]" : ""}>
                {currentFolderId ? "Remove from folder" : "None"}
              </span>
            </DropdownMenuItem>
            {folders.map((folder) => (
              <DropdownMenuItem
                key={folder.id}
                onClick={(e) => { e.stopPropagation(); onMoveToFolder(folder.id); }}
                className="cursor-pointer"
              >
                <span className={currentFolderId === folder.id ? "font-semibold text-[var(--accent-primary)]" : ""}>
                  {folder.name}
                </span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        {/* Tags */}
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="gap-2 cursor-pointer">
            <TagIcon size={13} />
            <span>Tags</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="w-48 max-h-60 overflow-y-auto scrollbar-thin p-1.5 space-y-0.5">
            <div className="px-2 py-1 text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Add Tag
            </div>
            {COLOR_OPTIONS.map((opt) => {
              const hasTag = tags.some((t) => t.name.toLowerCase() === opt.name.toLowerCase());
              return (
                <DropdownMenuItem
                  key={opt.name}
                  onClick={(e) => {
                    e.stopPropagation();
                    hasTag ? onRemoveTag(opt.name) : onAddTag({ name: opt.name, color: opt.color });
                  }}
                  className="flex items-center justify-between cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${opt.color}`} />
                    <span>{opt.name}</span>
                  </div>
                  {hasTag && (
                    <span className="text-[10px] text-[var(--accent-primary)] font-semibold">Applied</span>
                  )}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <DropdownMenuSeparator />

        <DropdownMenuItem
          onClick={(e) => { e.stopPropagation(); onRename(); }}
          className="gap-2 cursor-pointer"
        >
          <Pencil size={13} />
          <span>Rename</span>
        </DropdownMenuItem>

        <DropdownMenuItem
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="gap-2 text-[var(--accent-error)] focus:bg-red-500/10 focus:text-red-400 cursor-pointer"
        >
          <Trash size={13} />
          <span>Delete</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <DropdownMenuItem disabled className="gap-2 opacity-40 cursor-not-allowed">
                  <Copy size={13} />
                  <span>Duplicate</span>
                </DropdownMenuItem>
              </div>
            </TooltipTrigger>
            <TooltipContent side="left">Coming soon</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <DropdownMenuItem disabled className="gap-2 opacity-40 cursor-not-allowed">
                  <Archive size={13} />
                  <span>Archive</span>
                </DropdownMenuItem>
              </div>
            </TooltipTrigger>
            <TooltipContent side="left">Coming soon</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <DropdownMenuItem disabled className="gap-2 opacity-40 cursor-not-allowed">
                  <FileDown size={13} />
                  <span>Export</span>
                </DropdownMenuItem>
              </div>
            </TooltipTrigger>
            <TooltipContent side="left">Coming soon</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
