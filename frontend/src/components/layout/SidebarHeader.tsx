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
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "8px",
          padding: "12px 0",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <button
          onClick={onNewChat}
          style={{
            width: "40px",
            height: "40px",
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "10px",
            color: "#f5f5f5",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
          className="hover:bg-white/[0.10]"
          title="New Chat"
        >
          <Plus size={17} />
        </button>
        <button
          onClick={() => navigate("/documents")}
          style={{
            width: "40px",
            height: "40px",
            background: "transparent",
            border: "none",
            borderRadius: "10px",
            color: "var(--text-muted, #737373)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            transition: "all 0.15s ease",
          }}
          className="hover:text-zinc-300 hover:bg-white/[0.06]"
          title={`Documents (${documents.length})`}
        >
          <Database size={17} />
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        padding: "12px 16px 14px",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {/* New Chat Button */}
      <button
        onClick={onNewChat}
        style={{
          width: "100%",
          height: "42px",
          background: "rgba(255,255,255,0.05)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: "12px",
          color: "#e4e4e7",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "0 14px",
          cursor: "pointer",
          fontSize: "14px",
          fontWeight: 500,
          fontFamily: "inherit",
          transition: "all 0.15s ease",
          textAlign: "left",
        }}
        className="hover:bg-white/[0.09] hover:border-white/[0.12]"
      >
        <Plus size={16} style={{ flexShrink: 0, color: "#a3a3a3" }} />
        <span>New Chat</span>
      </button>

      {/* Documents Button */}
      <button
        onClick={() => navigate("/documents")}
        style={{
          width: "100%",
          height: "42px",
          background: "transparent",
          border: "none",
          borderRadius: "12px",
          color: "var(--text-secondary, #A3A3A3)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 14px",
          cursor: "pointer",
          fontSize: "14px",
          fontWeight: 500,
          fontFamily: "inherit",
          transition: "all 0.15s ease",
          textAlign: "left",
        }}
        className="hover:text-zinc-200 hover:bg-white/[0.05]"
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <Database size={15} style={{ flexShrink: 0, color: "var(--text-muted, #737373)" }} />
          <span>Documents</span>
        </div>
        <span
          style={{
            fontSize: "12px",
            fontFamily: "monospace",
            fontWeight: 600,
            color: "var(--text-muted, #737373)",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.06)",
            padding: "1px 7px",
            borderRadius: "5px",
            flexShrink: 0,
          }}
        >
          {documents.length}
        </span>
      </button>

      {/* Section label */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 4px 2px",
          fontSize: "11px",
          fontWeight: 600,
          color: "var(--text-muted, #737373)",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        <span>Conversations</span>
        <span style={{ fontFamily: "monospace", fontWeight: 700 }}>{conversations.length}</span>
      </div>

      {/* Search Box */}
      <div
        style={{
          position: "relative",
          display: "flex",
          alignItems: "center",
        }}
      >
        <Search
          size={13}
          style={{
            position: "absolute",
            left: "11px",
            color: "var(--text-muted, #737373)",
            pointerEvents: "none",
            flexShrink: 0,
          }}
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
          style={{
            width: "100%",
            height: "38px",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: "10px",
            paddingLeft: "34px",
            paddingRight: "60px",
            paddingTop: "0",
            paddingBottom: "0",
            color: "var(--text-primary, #F5F5F5)",
            fontSize: "13px",
            fontFamily: "inherit",
            outline: "none",
            transition: "border-color 0.15s ease, background 0.15s ease",
          }}
          className="placeholder:text-zinc-600 focus:border-white/[0.14] focus:bg-white/[0.06]"
        />
        {/* Keyboard shortcut hint */}
        <span
          style={{
            position: "absolute",
            right: "9px",
            display: "flex",
            alignItems: "center",
            gap: "2px",
          }}
        >
          <kbd
            style={{
              fontSize: "10px",
              fontFamily: "monospace",
              color: "var(--text-muted, #737373)",
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "4px",
              padding: "1px 4px",
              lineHeight: 1.4,
            }}
          >
            Ctrl+/
          </kbd>
        </span>
      </div>
    </div>
  );
};
