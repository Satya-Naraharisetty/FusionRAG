import React from "react";
import { useNavigate } from "react-router-dom";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "../ui/command";
import { useConversations } from "../../hooks/useConversations";
import { useAuth } from "../../hooks/useAuth";
import { MessageSquare, LayoutGrid, Settings, Plus, LogOut } from "lucide-react";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  open,
  onOpenChange,
}) => {
  const navigate = useNavigate();
  const { data: listData } = useConversations();
  const { logout } = useAuth();

  const conversations = listData?.conversations || [];

  const handleSelect = (callback: () => void) => {
    onOpenChange(false);
    callback();
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Type a command or search conversations..." />
      <CommandList className="bg-zinc-950 text-zinc-300 border-zinc-800">
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Actions">
          <CommandItem
            onSelect={() => handleSelect(() => navigate("/chat"))}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-zinc-900 focus:bg-zinc-900 rounded-md text-xs"
          >
            <Plus size={14} className="text-zinc-400" />
            <span>New Chat</span>
          </CommandItem>
          <CommandItem
            onSelect={() => handleSelect(() => navigate("/documents"))}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-zinc-900 focus:bg-zinc-900 rounded-md text-xs"
          >
            <LayoutGrid size={14} className="text-zinc-400" />
            <span>Documents</span>
          </CommandItem>
          <CommandItem
            onSelect={() => handleSelect(() => navigate("/settings"))}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-zinc-900 focus:bg-zinc-900 rounded-md text-xs"
          >
            <Settings size={14} className="text-zinc-400" />
            <span>Settings</span>
          </CommandItem>
          <CommandItem
            onSelect={() => handleSelect(() => logout())}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-red-950/20 focus:bg-red-950/20 text-red-400 hover:text-red-300 rounded-md text-xs"
          >
            <LogOut size={14} />
            <span>Logout</span>
          </CommandItem>
        </CommandGroup>

        {conversations.length > 0 && (
          <CommandGroup heading="Recent Conversations">
            {conversations.slice(0, 10).map((c) => (
              <CommandItem
                key={c.id}
                onSelect={() => handleSelect(() => navigate(`/chat/${c.id}`))}
                className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-zinc-900 focus:bg-zinc-900 rounded-md text-xs"
              >
                <MessageSquare size={14} className="text-zinc-500" />
                <span className="truncate">{c.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
};
