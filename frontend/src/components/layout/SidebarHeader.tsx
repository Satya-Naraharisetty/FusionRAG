import React from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Database, Search } from "lucide-react";
import { useDocuments } from "../../hooks/useDocuments";
import { Conversation } from "../../types";

interface SidebarHeaderProps {
  conversations: Conversation[];
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  onNewChat: () => void;
  collapsed: boolean;
}

export const SidebarHeader: React.FC<SidebarHeaderProps> = ({
  conversations,
  searchQuery,
  setSearchQuery,
  onNewChat,
  collapsed,
}) => {
  const navigate = useNavigate();
  const { data: documents = [] } = useDocuments();

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-2 py-3 border-b border-[var(--border-subtle)]">
        <button
          onClick={onNewChat}
          className="w-10 h-10 bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-elevated)] rounded-[var(--radius-lg)] text-[var(--text-primary)] flex items-center justify-center cursor-pointer transition-colors"
          title="New Chat"
        >
          <Plus size={16} />
        </button>
        <button
          onClick={() => navigate("/documents")}
          className="w-10 h-10 bg-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] rounded-[var(--radius-lg)] flex items-center justify-center cursor-pointer transition-colors"
          title={`Documents (${documents.length})`}
        >
          <Database size={16} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-3 border-b border-[var(--border-subtle)]">
      {/* New Chat Button */}
      <button
        onClick={onNewChat}
        className="w-full h-10 bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-elevated)] rounded-[var(--radius-lg)] text-[var(--text-primary)] flex items-center gap-2.5 px-3 cursor-pointer text-xs font-medium transition-colors text-left"
      >
        <Plus size={16} className="flex-shrink-0 text-[var(--text-secondary)]" />
        <span>New Chat</span>
      </button>

      {/* Documents Button */}
      <button
        onClick={() => navigate("/documents")}
        className="w-full h-10 bg-transparent hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded-[var(--radius-lg)] flex items-center justify-between px-3 cursor-pointer text-xs font-medium transition-colors text-left"
      >
        <div className="flex items-center gap-2.5">
          <Database size={15} className="flex-shrink-0 text-[var(--text-muted)]" />
          <span>Documents</span>
        </div>
        <span className="text-[11px] font-mono font-medium text-[var(--text-muted)] bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] px-1.5 py-0.5 rounded-[var(--radius-sm)] flex-shrink-0">
          {documents.length}
        </span>
      </button>

      {/* Section label */}
      <div className="flex items-center justify-between px-1 pt-1 text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
        <span>Conversations</span>
        <span className="font-mono text-[10px]">{conversations.length}</span>
      </div>

      {/* Search Box */}
      <div className="relative flex items-center">
        <Search
          size={13}
          className="absolute left-3 text-[var(--text-muted)] pointer-events-none flex-shrink-0"
        />
        <input
          id="sidebar-search-input"
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setSearchQuery("");
          }}
          placeholder="Search conversations..."
          className="w-full h-9 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-[var(--radius-lg)] pl-8 pr-12 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]/50 focus:ring-2 focus:ring-[var(--accent-primary)]/20 transition-all"
        />
        {/* Keyboard shortcut hint */}
        <span className="absolute right-2.5 flex items-center">
          <kbd className="text-[10px] font-mono text-[var(--text-muted)] bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded px-1.5 py-0.5 leading-none">
            Ctrl+/
          </kbd>
        </span>
      </div>
    </div>
  );
};
