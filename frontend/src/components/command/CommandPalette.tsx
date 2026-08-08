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
      <CommandList className="bg-[var(--bg-elevated)] text-[var(--text-primary)] border-[var(--border-subtle)]">
        <CommandEmpty className="py-6 text-center text-xs text-[var(--text-muted)]">No results found.</CommandEmpty>
        <CommandGroup heading="Actions">
          <CommandItem
            onSelect={() => handleSelect(() => navigate("/chat"))}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[var(--bg-tertiary)] data-[selected=true]:bg-[var(--bg-tertiary)] rounded-[var(--radius-md)] text-xs font-medium text-[var(--text-primary)]"
          >
            <Plus size={14} className="text-[var(--text-secondary)]" />
            <span>New Chat</span>
          </CommandItem>
          <CommandItem
            onSelect={() => handleSelect(() => navigate("/documents"))}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[var(--bg-tertiary)] data-[selected=true]:bg-[var(--bg-tertiary)] rounded-[var(--radius-md)] text-xs font-medium text-[var(--text-primary)]"
          >
            <LayoutGrid size={14} className="text-[var(--text-secondary)]" />
            <span>Documents</span>
          </CommandItem>
          <CommandItem
            onSelect={() => handleSelect(() => navigate("/settings"))}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[var(--bg-tertiary)] data-[selected=true]:bg-[var(--bg-tertiary)] rounded-[var(--radius-md)] text-xs font-medium text-[var(--text-primary)]"
          >
            <Settings size={14} className="text-[var(--text-secondary)]" />
            <span>Settings</span>
          </CommandItem>
          <CommandItem
            onSelect={() => handleSelect(() => logout())}
            className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-red-500/10 data-[selected=true]:bg-red-500/10 text-red-400 rounded-[var(--radius-md)] text-xs font-medium"
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
                className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[var(--bg-tertiary)] data-[selected=true]:bg-[var(--bg-tertiary)] rounded-[var(--radius-md)] text-xs text-[var(--text-primary)]"
              >
                <MessageSquare size={14} className="text-[var(--text-muted)]" />
                <span className="truncate">{c.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
};
