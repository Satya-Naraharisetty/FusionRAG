import React from "react";
import { MoreHorizontal, Pencil, Trash, FileDown, Archive, Copy, Share2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";

interface ConversationMenuProps {
  onRename: () => void;
  onDelete: () => void;
}

export const ConversationMenu: React.FC<ConversationMenuProps> = ({ onRename, onDelete }) => {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-7 w-7 items-center justify-center rounded-md hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 focus:outline-none"
          aria-label="More actions"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal size={16} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48 bg-zinc-950 border-zinc-800 text-zinc-300">
        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onRename(); }} className="gap-2 focus:bg-zinc-800 focus:text-zinc-100 cursor-pointer">
          <Pencil size={14} />
          <span>Rename</span>
        </DropdownMenuItem>
        
        <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onDelete(); }} className="gap-2 text-red-400 focus:bg-red-950/30 focus:text-red-300 cursor-pointer">
          <Trash size={14} />
          <span>Delete</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator className="bg-zinc-850" />

        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="relative">
                <DropdownMenuItem disabled className="gap-2 opacity-50 cursor-not-allowed">
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
                <DropdownMenuItem disabled className="gap-2 opacity-50 cursor-not-allowed">
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
                <DropdownMenuItem disabled className="gap-2 opacity-50 cursor-not-allowed">
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

        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="relative">
                <DropdownMenuItem disabled className="gap-2 opacity-50 cursor-not-allowed">
                  <Share2 size={14} />
                  <span>Share</span>
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
