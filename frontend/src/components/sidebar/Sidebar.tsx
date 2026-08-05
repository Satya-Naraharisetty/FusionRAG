import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import {
  useConversations,
  useRenameConversation,
  useDeleteConversation,
} from "../../hooks/useConversations";
import { useSidebarState } from "../../hooks/useSidebarState";
import { SidebarSearch } from "./SidebarSearch";
import { ConversationList } from "./ConversationList";
import {
  Plus,
  Settings,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  LayoutGrid,
} from "lucide-react";
import { Button } from "../ui/button";
import { Avatar, AvatarFallback } from "../ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { cn } from "../../lib/utils";

interface SidebarProps {
  className?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({ className }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { conversationId } = useParams<{ conversationId?: string }>();
  const [searchQuery, setSearchQuery] = useState("");

  const { collapsed, setCollapsed } = useSidebarState();
  const { data: listData, isLoading } = useConversations();

  const renameMutation = useRenameConversation();
  const deleteMutation = useDeleteConversation();

  const handleNewChat = () => {
    navigate("/chat");
  };

  const handleSelectConversation = (id: string) => {
    navigate(`/chat/${id}`);
  };

  const userInitials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : "US";

  const conversations = listData?.conversations || [];

  return (
    <aside
      className={cn(
        "flex flex-col bg-zinc-950 border-r border-zinc-800/80 h-full transition-all duration-300 relative z-20",
        collapsed ? "w-16" : "w-[260px]",
        className
      )}
    >
      {/* Top Header */}
      <div className="flex h-14 items-center justify-between px-3 border-b border-zinc-900/60">
        {!collapsed && (
          <div
            onClick={handleNewChat}
            className="flex items-center gap-2 cursor-pointer font-title font-bold text-zinc-100 text-sm pl-1.5"
          >
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-br from-violet-600 to-fuchsia-600 text-white font-extrabold text-xs">
              H
            </div>
            <span>Hybrid RAG</span>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            "h-8 w-8 hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200",
            collapsed && "mx-auto"
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </Button>
      </div>

      {/* Action Buttons */}
      <div className="p-3 flex flex-col gap-1.5">
        <Button
          onClick={handleNewChat}
          className={cn(
            "w-full bg-violet-600 hover:bg-violet-700 text-white text-xs font-semibold h-9 rounded-md transition-all duration-200 shadow-md",
            collapsed ? "px-0 justify-center" : "px-3 justify-start gap-2"
          )}
        >
          <Plus size={16} />
          {!collapsed && <span>New Chat</span>}
        </Button>
        
        <Button
          onClick={() => navigate("/documents")}
          variant="outline"
          className={cn(
            "w-full bg-zinc-900/50 border-zinc-800 text-zinc-300 hover:text-zinc-100 hover:bg-zinc-800 text-xs font-semibold h-9 rounded-md transition-all duration-200",
            collapsed ? "px-0 justify-center" : "px-3 justify-start gap-2"
          )}
        >
          <LayoutGrid size={16} />
          {!collapsed && <span>Documents</span>}
        </Button>
      </div>

      {/* Search Bar */}
      {!collapsed && (
        <SidebarSearch onSearch={(q) => setSearchQuery(q)} />
      )}

      {/* Conversations Scroll Area */}
      {collapsed ? (
        <div className="flex-1 flex flex-col items-center gap-2 pt-4">
          <div className="w-1.5 h-1.5 rounded-full bg-zinc-800" />
        </div>
      ) : isLoading ? (
        <div className="flex-1 px-3 py-4 flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div
              key={idx}
              className="h-8 bg-zinc-900/50 border border-zinc-800/20 rounded-md animate-pulse"
            />
          ))}
        </div>
      ) : (
        <ConversationList
          conversations={conversations}
          activeId={conversationId || null}
          onSelect={handleSelectConversation}
          onRename={async (id, title) => renameMutation.mutateAsync({ id, title })}
          onDelete={async (id) => deleteMutation.mutateAsync(id)}
          searchQuery={searchQuery}
        />
      )}

      {/* Bottom User Menu */}
      <div className="p-3 border-t border-zinc-900/60 mt-auto bg-zinc-950/80">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className={cn(
                "flex items-center w-full rounded-lg hover:bg-zinc-900 transition-all duration-200 focus:outline-none p-1.5",
                collapsed ? "justify-center" : "justify-between"
              )}
            >
              <div className="flex items-center gap-2 min-w-0">
                <Avatar className="h-7 w-7 bg-violet-650/40 border border-violet-550/30 text-violet-300">
                  <AvatarFallback className="text-[10px] font-bold bg-transparent">
                    {userInitials}
                  </AvatarFallback>
                </Avatar>
                {!collapsed && user && (
                  <div className="text-left min-w-0">
                    <p className="text-[11px] font-semibold text-zinc-300 truncate">
                      {user.email}
                    </p>
                    <span className="inline-flex items-center px-1 text-[8px] font-extrabold uppercase rounded bg-zinc-800 text-zinc-400">
                      {user.role}
                    </span>
                  </div>
                )}
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-[200px] bg-zinc-950 border-zinc-800 text-zinc-300">
            <DropdownMenuItem
              onClick={() => navigate("/settings")}
              className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer"
            >
              <Settings size={14} />
              <span>Settings</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator className="bg-zinc-900" />
            <DropdownMenuItem
              onClick={logout}
              className="gap-2 text-red-400 focus:bg-red-950/20 focus:text-red-300 cursor-pointer"
            >
              <LogOut size={14} />
              <span>Sign Out</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
};
