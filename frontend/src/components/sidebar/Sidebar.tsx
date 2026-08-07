import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import {
  useConversations,
  useRenameConversation,
  useDeleteConversation,
} from "../../hooks/useConversations";
import { useSidebarState } from "../../hooks/useSidebarState";
import { useLocalConversationMetadata } from "../../hooks/useLocalConversationMetadata";
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

  // Local metadata hook
  const {
    pinnedIds,
    folders,
    tags,
    togglePin,
    createFolder,
    renameFolder,
    deleteFolder,
    moveConversationToFolder,
    addTag,
    removeTag,
  } = useLocalConversationMetadata();

  // Touch gesture swipe handling
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];
    touchStart.current = { x: touch.clientX, y: touch.clientY };
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStart.current) return;
    const touch = e.touches[0];
    const diffX = touch.clientX - touchStart.current.x;
    const diffY = touch.clientY - touchStart.current.y;

    // Detect swiping
    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 40) {
      if (diffX > 0 && collapsed) {
        // swipe right -> expand
        setCollapsed(false);
        touchStart.current = null;
      } else if (diffX < 0 && !collapsed) {
        // swipe left -> collapse
        setCollapsed(true);
        touchStart.current = null;
      }
    }
  };

  // Keyboard shortcut for focusing search
  useEffect(() => {
    const handleGlobalKeys = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      if (e.key === "/" && !isInput) {
        e.preventDefault();
        const searchInput = document.getElementById("sidebar-search-input");
        if (searchInput) {
          searchInput.focus();
        }
      } else if (e.key === "Escape" && document.activeElement?.id === "sidebar-search-input") {
        const searchInput = document.getElementById("sidebar-search-input");
        if (searchInput) {
          searchInput.blur();
        }
      }
    };

    window.addEventListener("keydown", handleGlobalKeys);
    return () => window.removeEventListener("keydown", handleGlobalKeys);
  }, []);

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
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      className={cn(
        "flex flex-col bg-zinc-950 border-r border-zinc-800/80 h-full transition-all duration-300 relative z-20 select-none",
        collapsed ? "w-16" : "w-[260px]",
        className
      )}
    >
      {/* Top Header */}
      <div className="flex h-14 items-center justify-between px-3 border-b border-zinc-900/40">
        {!collapsed && (
          <div
            onClick={handleNewChat}
            className="flex items-center gap-2 cursor-pointer font-title font-bold text-zinc-100 text-sm pl-1.5 transition-transform duration-200 hover:scale-[1.02]"
          >
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-gradient-to-br from-violet-600 to-fuchsia-600 text-white font-extrabold text-xs shadow-md">
              H
            </div>
            <span className="bg-gradient-to-r from-zinc-100 to-zinc-350 bg-clip-text text-transparent">
              Hybrid RAG
            </span>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            "h-8 w-8 hover:bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 cursor-pointer transition-colors duration-200",
            collapsed && "mx-auto"
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
        </Button>
      </div>

      {/* Action Buttons */}
      <div className="p-3 flex flex-col gap-1.5">
        <Button
          onClick={handleNewChat}
          className={cn(
            "w-full bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:shadow-[0_0_15px_rgba(139,92,246,0.25)] border-0 text-white text-xs font-semibold h-9 rounded-lg transition-all duration-300 shadow-md cursor-pointer",
            collapsed ? "px-0 justify-center" : "px-3 justify-start gap-2"
          )}
        >
          <Plus size={15} />
          {!collapsed && <span>New Chat</span>}
        </Button>

        <Button
          onClick={() => navigate("/documents")}
          variant="outline"
          className={cn(
            "w-full bg-zinc-900/20 border-zinc-900 hover:border-zinc-800 text-zinc-300 hover:text-zinc-150 hover:bg-zinc-900/60 text-xs font-semibold h-9 rounded-lg transition-all duration-300 cursor-pointer",
            collapsed ? "px-0 justify-center" : "px-3 justify-start gap-2"
          )}
        >
          <LayoutGrid size={15} />
          {!collapsed && <span>Documents</span>}
        </Button>
      </div>

      {/* Search Bar */}
      {!collapsed && <SidebarSearch onSearch={(q) => setSearchQuery(q)} />}

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
          pinnedIds={pinnedIds}
          folders={folders}
          tags={tags}
          togglePin={togglePin}
          createFolder={createFolder}
          renameFolder={renameFolder}
          deleteFolder={deleteFolder}
          moveConversationToFolder={moveConversationToFolder}
          addTag={addTag}
          removeTag={removeTag}
        />
      )}

      {/* Bottom User Menu */}
      <div className="p-3 border-t border-zinc-900/40 mt-auto bg-zinc-950/40 backdrop-blur-md">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className={cn(
                "flex items-center w-full rounded-xl hover:bg-zinc-900/60 border border-transparent hover:border-zinc-850/40 transition-all duration-300 focus:outline-none p-1.5 cursor-pointer",
                collapsed ? "justify-center" : "justify-between"
              )}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <Avatar className="h-8 w-8 bg-violet-950/40 border border-violet-800/30 text-violet-300 shadow-[0_0_10px_rgba(139,92,246,0.15)] flex-shrink-0">
                  <AvatarFallback className="text-[11px] font-bold bg-transparent">
                    {userInitials}
                  </AvatarFallback>
                </Avatar>
                {!collapsed && user && (
                  <div className="text-left min-w-0">
                    <p className="text-[11px] font-bold text-zinc-200 truncate leading-tight">
                      {user.email}
                    </p>
                    <span className="inline-flex items-center px-1 py-0.5 mt-0.5 text-[8px] font-extrabold uppercase rounded bg-zinc-900 text-zinc-400 border border-zinc-800/30 tracking-wider">
                      {user.role}
                    </span>
                  </div>
                )}
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-[200px] bg-zinc-950 border-zinc-850 text-zinc-300">
            <DropdownMenuItem
              onClick={() => navigate("/settings")}
              className="gap-2 focus:bg-zinc-900 focus:text-zinc-100 cursor-pointer text-xs font-medium"
            >
              <Settings size={14} />
              <span>Settings</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator className="bg-zinc-900" />
            <DropdownMenuItem
              onClick={logout}
              className="gap-2 text-red-400 focus:bg-red-950/20 focus:text-red-300 cursor-pointer text-xs font-medium"
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
