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
    <header className="flex h-14 w-full items-center justify-between border-b border-zinc-200/50 dark:border-zinc-800/40 px-4 select-none bg-white dark:bg-[#212121] shrink-0 z-10 transition-colors">
      <div className="flex items-center gap-3">
        {collapsed && (
          <button
            onClick={() => setCollapsed(false)}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/60 transition-colors cursor-pointer"
            aria-label="Expand sidebar"
          >
            <PanelLeftOpen size={16} />
          </button>
        )}
        <div className="flex flex-col text-left">
          <h1 className="text-xs font-semibold text-zinc-800 dark:text-zinc-150 line-clamp-1 max-w-[200px] sm:max-w-[400px]">
            {title}
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-3.5">
        {/* Model Badge */}
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold bg-zinc-100 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-750 text-zinc-650 dark:text-zinc-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          {model}
        </span>

        {/* Connection status indicator */}
        <div className="flex items-center">
          {connectionLost ? (
            <span className="flex items-center gap-1 text-[10px] font-bold text-red-500 animate-pulse">
              <WifiOff size={12} />
              <span className="hidden sm:inline">Offline</span>
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] font-bold text-zinc-400 dark:text-zinc-500">
              <Wifi size={12} className="text-emerald-500" />
              <span className="hidden sm:inline">Connected</span>
            </span>
          )}
        </div>
      </div>
    </header>
  );
};
export default ChatToolbar;
