import React from "react";
import { PanelLeftOpen, WifiOff } from "lucide-react";
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
    <header className="h-[52px] flex items-center justify-between px-5 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)] flex-shrink-0 z-10">
      {/* Left */}
      <div className="flex items-center gap-2.5 min-w-0">
        {collapsed && (
          <button
            onClick={() => setCollapsed(false)}
            className="p-1.5 rounded-[var(--radius-md)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] cursor-pointer transition-colors border-none bg-transparent flex items-center justify-center"
            aria-label="Expand sidebar"
          >
            <PanelLeftOpen size={17} />
          </button>
        )}
        <h1 className="text-[15px] font-semibold text-[var(--text-primary)] truncate max-w-[420px]">
          {title}
        </h1>
      </div>

      {/* Right */}
      <div className="flex items-center gap-3.5 flex-shrink-0">
        {/* Model badge */}
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
          {model}
        </span>

        {/* Stream connection loss — browser offline is covered by OfflineBanner */}
        {connectionLost && (
          <span
            className="inline-flex items-center gap-1 text-xs font-medium text-red-400 animate-pulse"
            role="status"
            aria-live="polite"
          >
            <WifiOff size={12} />
            <span className="hidden sm:inline">Stream disconnected</span>
          </span>
        )}
      </div>
    </header>
  );
};

export default ChatToolbar;
