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
        "flex flex-col h-full bg-[var(--bg-secondary)] transition-all duration-200 relative z-20 select-none",
        collapsed ? "w-16" : "w-[272px]",
        className
      )}
    >
      {/* Sidebar Header & Toggle Section */}
      <div
        className={cn(
          "flex items-center px-3 shrink-0 h-14",
          collapsed ? "justify-center" : "justify-between"
        )}
      >
        {!collapsed && (
          <div
            onClick={handleNewChat}
            className="flex cursor-pointer items-center gap-2.5 pl-1 transition-opacity hover:opacity-90"
          >
            <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-xs font-semibold text-[var(--text-primary)] shadow-none">
              <span className="font-title">N</span>
            </div>
            <span className="font-title text-sm font-semibold tracking-tight text-[var(--text-primary)]">NexusRAG</span>
          </div>
        )}
        <Button
          variant="ghost"
          size="iconSm"
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            "text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]",
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
          <div className="h-1.5 w-1.5 rounded-full bg-[var(--border-default)]" />
        </div>
      ) : isLoading ? (
        <div className="flex-1 px-2.5 py-3 flex flex-col gap-1.5">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div
              key={idx}
              className="h-8 bg-[var(--bg-tertiary)]/40 border border-[var(--border-subtle)] rounded-[var(--radius-md)] skeleton-shimmer"
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
