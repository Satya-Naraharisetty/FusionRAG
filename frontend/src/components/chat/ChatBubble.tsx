import React, { useState, useRef } from "react";
import { Copy, Check, RefreshCw, Clock, ThumbsUp, ThumbsDown, Flag } from "lucide-react";
import { ChatMessage } from "../../types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { CitationCard } from "./CitationCard";
import { ToolCallCard } from "./ToolCallCard";
import { StreamingCursor } from "./StreamingCursor";
import { Avatar, AvatarFallback } from "../ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { cn } from "../../lib/utils";

interface ChatBubbleProps {
  message: ChatMessage;
  onRetry?: () => void;
  onReact?: (messageId: string, reaction: "up" | "down" | "flag") => void;
}

export const ChatBubble: React.FC<ChatBubbleProps> = ({ message, onRetry, onReact }) => {
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

  const initials = isUser ? "U" : "AI";
  const messageTime = message.created_at ? new Date(message.created_at) : new Date();
  const formattedTimeStr = messageTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const fullTimeStr = messageTime.toLocaleString();

  if (isUser) {
    return (
      <TooltipProvider>
        <div
          ref={contentRef}
          className="flex w-full py-2 select-none group justify-center"
          role="article"
          aria-label="User message"
        >
          <div className="w-full max-w-3xl flex justify-end px-4 md:px-6">
            <div className="flex flex-col items-end gap-1 max-w-[70%]">
              <div className="relative px-4 py-2.5 rounded-[22px] bg-zinc-800 text-zinc-100 text-xs md:text-sm select-text leading-relaxed font-sans shadow-xs border border-zinc-700/20">
                {message.content ? (
                  <MarkdownRenderer content={message.content} />
                ) : null}
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="text-[10px] text-zinc-500 mr-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 cursor-default">
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
        className="flex w-full py-6 select-none group bg-transparent transition-all duration-200 ease-standard justify-center"
        role="article"
        aria-label="Assistant response"
        onMouseEnter={() => setShowActions(true)}
        onMouseLeave={() => setShowActions(false)}
      >
        <div className="w-full max-w-3xl flex gap-4 px-4 md:px-6 items-start">
          {/* Avatar */}
          <Avatar
            className="h-8 w-8 flex-shrink-0 border bg-violet-950/40 border-violet-900/30 text-violet-300 transition-all duration-200 hover:shadow-[0_0_12px_rgba(139,92,246,0.3)] rounded-full"
          >
            <AvatarFallback className="text-xs font-bold bg-transparent">
              {initials}
            </AvatarFallback>
          </Avatar>

          {/* Message content area */}
          <div className="flex-1 flex flex-col gap-2 min-w-0">
            {/* Tool calls execution log */}
            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="flex flex-col gap-1.5 w-full">
                {message.toolCalls.map((tc) => (
                  <ToolCallCard key={tc.id} toolCall={tc} />
                ))}
              </div>
            )}

            {/* Content */}
            <div className="flex flex-col gap-1.5 select-text text-zinc-150 text-xs md:text-sm leading-relaxed font-sans">
              {message.content ? (
                <MarkdownRenderer content={message.content} />
              ) : message.status === "pending" ? (
                <div className="flex items-center gap-2 text-zinc-500 text-xs py-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-zinc-550 animate-bounce" />
                  <span className="h-1.5 w-1.5 rounded-full bg-zinc-550 animate-bounce delay-150" />
                  <span className="h-1.5 w-1.5 rounded-full bg-zinc-550 animate-bounce delay-300" />
                </div>
              ) : message.status === "failed" && message.error ? (
                <div className="text-red-400 bg-red-950/15 border border-red-900/30 rounded-xl p-3 text-xs flex flex-col gap-1 max-w-xl animate-fade-in font-sans">
                  <span className="font-bold flex items-center gap-1.5">
                    <span className="text-red-500">⚠</span> Generation Failed
                  </span>
                  <span className="text-[10px] text-zinc-400 leading-normal">{message.error}</span>
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

            {/* Message footer: timestamp, reactions, actions */}
            <div
              className={cn(
                "flex items-center justify-between gap-2 mt-2 pt-1.5",
                "opacity-0 group-hover:opacity-100 transition-opacity duration-200",
                showActions && "opacity-100"
              )}
            >
              {/* Timestamp */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    className="flex items-center gap-1 text-[10px] font-medium text-zinc-500 hover:text-zinc-300 transition-colors"
                    aria-label="Message time"
                  >
                    <Clock size={10} className="opacity-60" />
                    <span>{formattedTimeStr}</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" align="center" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                  {fullTimeStr}
                </TooltipContent>
              </Tooltip>

              {/* Reactions (assistant only) */}
              {!isUser && message.status !== "streaming" && (
                <div className="flex items-center gap-1">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => handleReact("up")}
                        className="flex items-center gap-1 p-1 rounded-lg text-zinc-500 hover:text-emerald-400 hover:bg-emerald-950/20 transition-all"
                        aria-label="Helpful"
                      >
                        <ThumbsUp size={12} />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                      Mark as helpful
                    </TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => handleReact("down")}
                        className="flex items-center gap-1 p-1 rounded-lg text-zinc-500 hover:text-red-400 hover:bg-red-950/20 transition-all"
                        aria-label="Not helpful"
                      >
                        <ThumbsDown size={12} />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                      Mark as not helpful
                    </TooltipContent>
                  </Tooltip>
                </div>
              )}

              {/* Actions: Copy, Flag, Retry */}
              <div className="flex items-center gap-1 ml-auto">
                {message.content && !isUser && message.status !== "streaming" && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={handleCopy}
                        className="flex items-center gap-1 p-1 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-all"
                        aria-label={copied ? "Copied to clipboard" : "Copy message"}
                      >
                        {copied ? (
                          <>
                            <Check size={11} className="text-emerald-400" />
                            <span className="text-[10px] text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <Copy size={11} />
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300">
                      {copied ? "Copied!" : "Copy message"}
                    </TooltipContent>
                  </Tooltip>
                )}

                {!isUser && message.status !== "streaming" && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => handleReact("flag")}
                        className="flex items-center gap-1 p-1 rounded-lg text-zinc-500 hover:text-amber-400 hover:bg-amber-950/20 transition-all"
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
                        className="flex items-center gap-1 p-1 rounded-lg text-red-400 hover:text-red-300 hover:bg-red-950/20 transition-all"
                        aria-label="Retry query"
                      >
                        <RefreshCw size={11} />
                        <span className="text-[10px] font-semibold">Retry</span>
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