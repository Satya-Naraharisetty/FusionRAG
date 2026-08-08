import React, { useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import {
  useConversations,
  useRenameConversation,
  useDeleteConversation,
} from "../../hooks/useConversations";
import { useSidebarState } from "../../hooks/useSidebarState";
import { useLocalConversationMetadata } from "../../hooks/useLocalConversationMetadata";
import { SidebarHeader } from "./SidebarHeader";
import { SidebarConversationList } from "./SidebarConversationList";
import { SidebarProfile } from "./SidebarProfile";
import { Button } from "../ui/Button";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
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

    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 40) {
      if (diffX > 0 && collapsed) {
        setCollapsed(false);
        touchStart.current = null;
      } else if (diffX < 0 && !collapsed) {
        setCollapsed(true);
        touchStart.current = null;
      }
    }
  };

  const handleNewChat = () => {
    navigate("/chat");
  };

  const handleSelectConversation = (id: string) => {
    navigate(`/chat/${id}`);
  };

  const conversations = listData?.conversations || [];

  return (
    <aside
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      className={cn(
        "flex flex-col h-full bg-[#171717] dark:bg-[#171717] light:bg-[#f9f9f9] border-r border-white/[0.07] transition-all duration-300 relative z-20 select-none",
        collapsed ? "w-16" : "w-[272px]",
        className
      )}
    >
      {/* Sidebar Header & Toggle Section */}
      <div
        className={cn(
          "flex items-center px-3 shrink-0",
          collapsed ? "h-14 justify-center" : "h-14 justify-between"
        )}
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        {!collapsed && (
          <div
            onClick={handleNewChat}
            style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", paddingLeft: "4px" }}
            className="hover:opacity-90 transition-opacity"
          >
            <div
              style={{
                width: "28px",
                height: "28px",
                borderRadius: "8px",
                background: "linear-gradient(135deg, hsl(250,84%,63%) 0%, hsl(282,84%,60%) 100%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <span style={{ color: "white", fontWeight: 800, fontSize: "13px", fontFamily: "var(--font-title, Outfit, Inter, sans-serif)" }}>H</span>
            </div>
            <span style={{ fontWeight: 700, fontSize: "15px", color: "#e4e4e7", letterSpacing: "-0.01em", fontFamily: "var(--font-title, Outfit, Inter, sans-serif)" }}>Hybrid RAG</span>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            "h-8 w-8 text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.06] cursor-pointer transition-colors duration-200",
            collapsed && "mx-auto"
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </Button>
      </div>

      {/* Main Top Header Controls */}
      <SidebarHeader
        conversations={conversations}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        onNewChat={handleNewChat}
        collapsed={collapsed}
      />

      {/* Scrollable Conversations List */}
      {collapsed ? (
        <div className="flex-1 flex flex-col items-center gap-2 pt-4">
          <div className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
        </div>
      ) : isLoading ? (
        <div className="flex-1 px-3 py-4 flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div
              key={idx}
              className="h-8 bg-zinc-800/20 border border-zinc-800/10 rounded-md animate-pulse"
            />
          ))}
        </div>
      ) : (
        <SidebarConversationList
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

      {/* Bottom Profile dropdown block */}
      <SidebarProfile
        user={user}
        logout={logout}
        collapsed={collapsed}
      />
    </aside>
  );
};
