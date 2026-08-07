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
} from "../ui/dropdown-menu";
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
  { name: "Violet", color: "bg-violet-500" },
  { name: "Emerald", color: "bg-emerald-500" },
  { name: "Rose", color: "bg-rose-500" },
  { name: "Amber", color: "bg-amber-500" },
  { name: "Blue", color: "bg-blue-500" },
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
          className="flex h-7 w-7 items-center justify-center rounded-md hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 focus:outline-none cursor-pointer"
          aria-label="More actions"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal size={16} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52 bg-zinc-950 border-zinc-850 text-zinc-300">
        {/* Pin / Unpin */}
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin();
          }}
          className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-xs"
        >
          <Pin size={14} className={isPinned ? "fill-violet-500 text-violet-500" : ""} />
          <span>{isPinned ? "Unpin Conversation" : "Pin Conversation"}</span>
        </DropdownMenuItem>

        {/* Move to Folder Submenu */}
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="gap-2 text-xs cursor-pointer focus:bg-zinc-900">
            <FolderOpen size={14} />
            <span>Move to Folder</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="bg-zinc-950 border-zinc-850 text-zinc-300 w-44">
            <DropdownMenuItem
              onClick={(e) => {
                e.stopPropagation();
                onMoveToFolder(null);
              }}
              className="text-xs cursor-pointer focus:bg-zinc-900"
            >
              <span className={!currentFolderId ? "font-bold text-violet-400" : ""}>
                No Folder
              </span>
            </DropdownMenuItem>
            {folders.map((folder) => (
              <DropdownMenuItem
                key={folder.id}
                onClick={(e) => {
                  e.stopPropagation();
                  onMoveToFolder(folder.id);
                }}
                className="text-xs cursor-pointer focus:bg-zinc-900"
              >
                <span className={currentFolderId === folder.id ? "font-bold text-violet-400" : ""}>
                  {folder.name}
                </span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        {/* Tags Submenu */}
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="gap-2 text-xs cursor-pointer focus:bg-zinc-900">
            <TagIcon size={14} />
            <span>Tags</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="bg-zinc-950 border-zinc-850 text-zinc-300 w-48 p-1.5 space-y-1">
            <div className="text-[10px] font-bold text-zinc-500 px-2 py-0.5 uppercase tracking-wider">
              Add Tag
            </div>
            {COLOR_OPTIONS.map((opt) => {
              const hasTag = tags.some((t) => t.name.toLowerCase() === opt.name.toLowerCase());
              return (
                <DropdownMenuItem
                  key={opt.name}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (hasTag) {
                      onRemoveTag(opt.name);
                    } else {
                      onAddTag({ name: opt.name, color: opt.color });
                    }
                  }}
                  className="flex items-center justify-between text-xs cursor-pointer focus:bg-zinc-900"
                >
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${opt.color}`} />
                    <span>{opt.name}</span>
                  </div>
                  {hasTag && <span className="text-[10px] text-violet-400 font-bold">Applied</span>}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <DropdownMenuSeparator className="bg-zinc-850" />

        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onRename();
          }}
          className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-xs"
        >
          <Pencil size={14} />
          <span>Rename</span>
        </DropdownMenuItem>

        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="gap-2 text-red-400 focus:bg-red-950/30 focus:text-red-300 cursor-pointer text-xs"
        >
          <Trash size={14} />
          <span>Delete</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator className="bg-zinc-850" />

        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="relative">
                <DropdownMenuItem disabled className="gap-2 opacity-50 cursor-not-allowed text-xs">
                  <Copy size={14} />
                  <span>Duplicate</span>
                </DropdownMenuItem>
              </div>
            </TooltipTrigger>
            <TooltipContent side="left" className="bg-zinc-900 border-zinc-800 text-zinc-300 text-xs">
              Coming soon
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="relative">
                <DropdownMenuItem disabled className="gap-2 opacity-50 cursor-not-allowed text-xs">
                  <Archive size={14} />
                  <span>Archive</span>
                </DropdownMenuItem>
              </div>
            </TooltipTrigger>
            <TooltipContent side="left" className="bg-zinc-900 border-zinc-800 text-zinc-300 text-xs">
              Coming soon
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="relative">
                <DropdownMenuItem disabled className="gap-2 opacity-50 cursor-not-allowed text-xs">
                  <FileDown size={14} />
                  <span>Export</span>
                </DropdownMenuItem>
              </div>
            </TooltipTrigger>
            <TooltipContent side="left" className="bg-zinc-900 border-zinc-800 text-zinc-300 text-xs">
              Coming soon
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
