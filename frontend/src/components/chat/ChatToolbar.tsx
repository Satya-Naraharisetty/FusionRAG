import React from "react";
import { PanelLeftOpen, Wifi, WifiOff } from "lucide-react";
import { useSidebarState } from "../../hooks/useSidebarState";

interface ChatToolbarProps {
  title?: string;
  model?: string;
  connectionLost?: boolean;
}

export const ChatToolbar: React.FC<ChatToolbarProps> = ({
  title = "New Chat",
  model = "Hybrid RAG v1",
  connectionLost = false,
}) => {
  const { collapsed, setCollapsed } = useSidebarState();

  return (
    <header
      style={{
        height: "52px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 20px",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        background: "var(--bg-primary, #0D0D0D)",
        flexShrink: 0,
        zIndex: 10,
      }}
    >
      {/* Left: expand button (when collapsed) + title */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
        {collapsed && (
          <button
            onClick={() => setCollapsed(false)}
            style={{
              padding: "6px",
              borderRadius: "8px",
              color: "var(--text-muted, #737373)",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "color 0.15s ease, background 0.15s ease",
            }}
            className="hover:text-zinc-300 hover:bg-zinc-800/60"
            aria-label="Expand sidebar"
          >
            <PanelLeftOpen size={17} />
          </button>
        )}
        <h1
          style={{
            fontSize: "15px",
            fontWeight: 600,
            color: "var(--text-primary, #F5F5F5)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            maxWidth: "420px",
          }}
        >
          {title}
        </h1>
      </div>

      {/* Right: model + connection status */}
      <div style={{ display: "flex", alignItems: "center", gap: "14px", flexShrink: 0 }}>
        {/* Model badge — subtle */}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "12px",
            fontWeight: 500,
            color: "var(--text-muted, #737373)",
          }}
        >
          <span
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: "#34d399",
              flexShrink: 0,
            }}
          />
          {model}
        </span>

        {/* Connection status — very subtle */}
        {connectionLost ? (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "12px",
              fontWeight: 500,
              color: "#f87171",
            }}
            className="animate-pulse"
          >
            <WifiOff size={12} />
            <span className="hidden sm:inline">Offline</span>
          </span>
        ) : (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "12px",
              fontWeight: 500,
              color: "var(--text-muted, #737373)",
            }}
          >
            <Wifi size={12} style={{ color: "#34d399" }} />
            <span className="hidden sm:inline">Connected</span>
          </span>
        )}
      </div>
    </header>
  );
};
export default ChatToolbar;
