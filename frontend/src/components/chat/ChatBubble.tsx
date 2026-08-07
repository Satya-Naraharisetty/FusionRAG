import React, { useState } from "react";
import { Copy, Check, RefreshCw } from "lucide-react";
import { ChatMessage } from "../../types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { CitationCard } from "./CitationCard";
import { ToolCallCard } from "./ToolCallCard";
import { StreamingCursor } from "./StreamingCursor";
import { Avatar, AvatarFallback } from "../ui/avatar";
import { cn } from "../../lib/utils";

interface ChatBubbleProps {
  message: ChatMessage;
  onRetry?: () => void;
}

export const ChatBubble: React.FC<ChatBubbleProps> = ({ message, onRetry }) => {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const initials = isUser ? "U" : "AI";

  return (
    <div
      className={cn(
        "flex w-full gap-3 py-6 px-4 md:px-6 select-none group",
        isUser ? "bg-transparent flex-row-reverse" : "bg-zinc-900/10 border-y border-zinc-900/40 backdrop-blur-xs border-l-2 border-l-violet-600/30"
      )}
      role="article"
      aria-label={isUser ? "User message" : "Assistant response"}
    >
      {/* Avatar */}
      <Avatar
        className={cn(
          "h-8 w-8 flex-shrink-0 border",
          isUser
            ? "bg-zinc-800 border-zinc-700 text-zinc-300"
            : "bg-violet-950/40 border-violet-900/30 text-violet-300"
        )}
      >
        <AvatarFallback className="text-xs font-bold bg-transparent">
          {initials}
        </AvatarFallback>
      </Avatar>

      {/* Message content area */}
      <div className="flex-1 flex flex-col gap-2 min-w-0 max-w-3xl">
        {/* Tool calls execution log */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="flex flex-col gap-1 w-full">
            {message.toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Content */}
        <div className="flex flex-col gap-1 select-text">
          {message.content ? (
            <MarkdownRenderer content={message.content} />
          ) : message.status === "pending" ? (
            <div className="flex items-center gap-2 text-zinc-500 text-xs">
              <span className="h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce" />
              <span className="h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce delay-150" />
              <span className="h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce delay-300" />
            </div>
          ) : null}

          {/* Blink cursor during streaming */}
          {message.status === "streaming" && <StreamingCursor />}
        </div>

        {/* Citations below assistant responses */}
        {message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3 select-text">
            {message.citations.map((c, idx) => (
              <CitationCard key={c.chunk_id || idx} citation={c} index={idx} />
            ))}
          </div>
        )}

        {/* Action icons bar */}
        {message.content && !isUser && message.status !== "streaming" && (
          <div className="flex items-center gap-2 mt-4 opacity-0 group-hover:opacity-100 hover:opacity-100 transition-opacity duration-200">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 text-[10px] font-semibold text-zinc-500 hover:text-zinc-300"
              title="Copy message"
            >
              {copied ? (
                <>
                  <Check size={11} className="text-emerald-400" />
                  <span className="text-emerald-400">Copied</span>
                </>
              ) : (
                <>
                  <Copy size={11} />
                  <span>Copy</span>
                </>
              )}
            </button>
            {message.status === "failed" && onRetry && (
              <button
                onClick={onRetry}
                className="flex items-center gap-1 text-[10px] font-semibold text-red-400 hover:text-red-300"
                title="Retry query"
              >
                <RefreshCw size={11} />
                <span>Retry</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
