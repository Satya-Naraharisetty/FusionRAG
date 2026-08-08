import React from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Database } from "lucide-react";
import { Button } from "../ui/Button";
import { SearchBox } from "../ui/SearchBox";
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
      <div className="flex flex-col items-center gap-3 py-3 border-b border-zinc-800/40">
        <Button
          onClick={onNewChat}
          size="icon"
          className="h-9 w-9 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 rounded-lg flex items-center justify-center cursor-pointer transition-colors shadow-sm"
          title="New Chat"
        >
          <Plus size={16} />
        </Button>
        <Button
          onClick={() => navigate("/documents")}
          size="icon"
          variant="ghost"
          className="h-9 w-9 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 rounded-lg flex items-center justify-center cursor-pointer transition-colors"
          title={`Documents (${documents.length})`}
        >
          <Database size={16} />
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3.5 p-3.5 border-b border-zinc-800/40">
      {/* Action Buttons */}
      <div className="flex flex-col gap-1.5">
        <Button
          onClick={onNewChat}
          className="w-full bg-zinc-800/40 hover:bg-zinc-800/85 border border-zinc-800/80 hover:border-zinc-700/40 text-zinc-200 text-xs font-medium h-10 rounded-xl flex items-center justify-start gap-2 px-3.5 transition-all cursor-pointer"
        >
          <Plus size={15} />
          <span>New Chat</span>
        </Button>

        <Button
          onClick={() => navigate("/documents")}
          variant="ghost"
          className="w-full text-zinc-450 hover:text-zinc-200 hover:bg-zinc-800/30 text-xs font-medium h-10 rounded-xl flex items-center justify-between px-3.5 transition-all cursor-pointer"
        >
          <div className="flex items-center gap-2">
            <Database size={14} className="text-zinc-500" />
            <span>Documents</span>
          </div>
          <span className="text-[10px] bg-zinc-900 text-zinc-500 border border-zinc-850 px-1.5 py-0.5 rounded font-mono font-bold">
            {documents.length}
          </span>
        </Button>
      </div>

      {/* Info label and search bar */}
      <div className="flex flex-col gap-1.5 mt-1">
        <div className="flex items-center justify-between text-[10px] font-bold text-zinc-500 uppercase tracking-widest px-1">
          <span>Conversations</span>
          <span className="font-mono">{conversations.length}</span>
        </div>
        <SearchBox
          placeholder="Search conversations..."
          value={searchQuery}
          onChange={setSearchQuery}
          onClear={() => setSearchQuery("")}
          id="sidebar-search-input"
          className="w-full h-8.5 text-zinc-250 bg-zinc-900/30 border-zinc-800/80 hover:border-zinc-750 focus-visible:ring-zinc-700"
        />
      </div>
    </div>
  );
};
