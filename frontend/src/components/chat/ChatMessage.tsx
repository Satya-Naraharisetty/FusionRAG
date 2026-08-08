import React, { useState, useRef } from "react";
import { Copy, Check, RefreshCw, Clock, ThumbsUp, ThumbsDown, Flag, Sparkles } from "lucide-react";
import { ChatMessage as ChatMessageType } from "../../types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { CitationCard } from "./CitationCard";
import { ToolCallCard } from "./ToolCallCard";
import { StreamingCursor } from "./StreamingCursor";
import { Avatar, AvatarFallback } from "../ui/Avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { cn } from "../../lib/utils";

interface ChatMessageProps {
  message: ChatMessageType;
  onRetry?: () => void;
  onReact?: (messageId: string, reaction: "up" | "down" | "flag") => void;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message, onRetry, onReact }) => {
  const [copied, setCopied] = useState(false);
  const [showActions, setShowActions] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const isUser = message.role === "user";

  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleReact = (reaction: "up" | "down" | "flag") => {
    onReact?.(message.id || "", reaction);
  };

  const messageTime = message.created_at ? new Date(message.created_at) : new Date();
  const formattedTimeStr = messageTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const fullTimeStr = messageTime.toLocaleString();

  if (isUser) {
    return (
      <TooltipProvider>
        <div
          ref={contentRef}
          className="flex w-full py-4 select-none group justify-center bg-transparent"
          role="article"
          aria-label="User message"
        >
          <div className="w-full max-w-[780px] flex justify-end px-6">
            <div className="flex flex-col items-end gap-1.5 max-w-[72%]">
              <div
                style={{
                  padding: "12px 16px",
                  borderRadius: "18px",
                  background: "var(--bg-tertiary, #1E1E1E)",
                  color: "var(--text-primary, #F5F5F5)",
                  fontSize: "15px",
                  lineHeight: 1.6,
                  fontFamily: "inherit",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
                className="select-text"
              >
                {message.content ? (
                  <MarkdownRenderer content={message.content} />
                ) : null}
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    style={{ fontSize: "11px", color: "var(--text-muted, #737373)", marginRight: "6px" }}
                    className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 cursor-default"
                  >
                    {formattedTimeStr}
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top" align="center" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                  {fullTimeStr}
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
        </div>
      </TooltipProvider>
    );
  }

  return (
    <TooltipProvider>
      <div
        ref={contentRef}
        className="flex w-full py-6 select-none group bg-transparent justify-center transition-colors"
        role="article"
        aria-label="Assistant response"
        onMouseEnter={() => setShowActions(true)}
        onMouseLeave={() => setShowActions(false)}
      >
        <div className="w-full max-w-[780px] flex gap-4 px-6 items-start">
          {/* Avatar Icon */}
          <Avatar
            style={{
              width: "32px",
              height: "32px",
              flexShrink: 0,
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.09)",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <AvatarFallback className="bg-transparent">
              <Sparkles size={14} className="text-zinc-300" />
            </AvatarFallback>
          </Avatar>

          {/* Message content area */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "10px", minWidth: 0 }}>
            {/* Tool calls execution log */}
            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="flex flex-col gap-1.5 w-full">
                {message.toolCalls.map((tc) => (
                  <ToolCallCard key={tc.id} toolCall={tc} />
                ))}
              </div>
            )}

            {/* Markdown Text Content */}
            <div className="flex flex-col gap-1.5 select-text" style={{ fontSize: "15px", lineHeight: 1.65, color: "var(--text-primary, #F5F5F5)", fontFamily: "inherit" }}>
              {message.content ? (
                <MarkdownRenderer content={message.content} />
              ) : message.status === "pending" ? (
                <div className="flex items-center gap-1.5 text-zinc-400 dark:text-zinc-550 text-xs py-2 pl-0.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-zinc-400 dark:bg-zinc-600 animate-bounce" />
                  <span className="h-1.5 w-1.5 rounded-full bg-zinc-400 dark:bg-zinc-600 animate-bounce delay-150" />
                  <span className="h-1.5 w-1.5 rounded-full bg-zinc-400 dark:bg-zinc-600 animate-bounce delay-300" />
                </div>
              ) : message.status === "failed" && message.error ? (
                <div className="text-red-650 dark:text-red-400 bg-red-50 dark:bg-red-950/15 border border-red-200/50 dark:border-red-900/30 rounded-xl p-3 text-xs flex flex-col gap-1 max-w-xl animate-fade-in font-sans">
                  <span className="font-bold flex items-center gap-1.5">
                    <span>⚠</span> Generation Failed
                  </span>
                  <span className="text-[10px] text-zinc-500 dark:text-zinc-400 leading-normal">{message.error}</span>
                </div>
              ) : null}

              {/* Blink cursor during streaming */}
              {message.status === "streaming" && <StreamingCursor />}
            </div>

            {/* Citations below assistant responses */}
            {message.citations && message.citations.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2.5 select-text">
                {message.citations.map((c, idx) => (
                  <CitationCard key={c.chunk_id || idx} citation={c} index={idx} />
                ))}
              </div>
            )}

            {/* Actions Panel */}
            <div
              className={cn(
                "flex items-center justify-between gap-2 mt-3 pt-1 border-t border-transparent",
                "opacity-0 group-hover:opacity-100 transition-opacity duration-200",
                showActions && "opacity-100"
              )}
            >
              {/* Left Actions - Time & Feedback */}
              <div className="flex items-center gap-1">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button className="flex items-center gap-1 text-[10px] text-zinc-400 dark:text-zinc-550 mr-1.5 cursor-default">
                      <Clock size={10} className="opacity-60" />
                      <span>{formattedTimeStr}</span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="center" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-355">
                    {fullTimeStr}
                  </TooltipContent>
                </Tooltip>

                {!isUser && message.status !== "streaming" && (
                  <>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => handleReact("up")}
                          className="p-1 rounded-lg text-zinc-400 dark:text-zinc-550 hover:text-emerald-500 dark:hover:text-emerald-450 hover:bg-zinc-100 dark:hover:bg-zinc-800/40 transition-colors"
                          aria-label="Helpful"
                        >
                          <ThumbsUp size={11} />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                        Helpful
                      </TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => handleReact("down")}
                          className="p-1 rounded-lg text-zinc-400 dark:text-zinc-550 hover:text-red-500 dark:hover:text-red-450 hover:bg-zinc-100 dark:hover:bg-zinc-800/40 transition-colors"
                          aria-label="Not helpful"
                        >
                          <ThumbsDown size={11} />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                        Not helpful
                      </TooltipContent>
                    </Tooltip>
                  </>
                )}
              </div>

              {/* Right Actions - Copy, Flag, Retry */}
              <div className="flex items-center gap-1 ml-auto">
                {message.content && !isUser && message.status !== "streaming" && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={handleCopy}
                        className="flex items-center gap-1 p-1 rounded-lg text-zinc-400 dark:text-zinc-550 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800/40 transition-colors"
                        aria-label={copied ? "Copied" : "Copy message"}
                      >
                        {copied ? (
                          <>
                            <Check size={11} className="text-emerald-500" />
                            <span className="text-[10px] text-emerald-555">Copied</span>
                          </>
                        ) : (
                          <Copy size={11} />
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                      {copied ? "Copied!" : "Copy response"}
                    </TooltipContent>
                  </Tooltip>
                )}

                {!isUser && message.status !== "streaming" && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => handleReact("flag")}
                        className="p-1 rounded-lg text-zinc-400 dark:text-zinc-550 hover:text-amber-500 dark:hover:text-amber-450 hover:bg-zinc-100 dark:hover:bg-zinc-800/40 transition-colors"
                        aria-label="Report issue"
                      >
                        <Flag size={11} />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                      Report issue
                    </TooltipContent>
                  </Tooltip>
                )}

                {message.status === "failed" && onRetry && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={onRetry}
                        className="flex items-center gap-1 p-1.5 rounded-lg text-red-500 hover:text-red-450 hover:bg-red-50 dark:hover:bg-red-950/20 transition-all font-semibold"
                        aria-label="Retry query"
                      >
                        <RefreshCw size={11} />
                        <span className="text-[10px]">Retry</span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                      Retry query
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
};
export default ChatMessage;
