import React, { lazy, Suspense, useState, useRef } from "react";
import { Copy, Check, RefreshCw, Clock, ThumbsUp, ThumbsDown, Flag, Sparkles, FileQuestion } from "lucide-react";
import { ChatMessage as ChatMessageType } from "../../types";
import { CitationCard } from "./CitationCard";
import { ToolCallCard } from "./ToolCallCard";
import { StreamingCursor } from "./StreamingCursor";
import { Avatar, AvatarFallback } from "../ui/Avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { cn } from "../../lib/utils";

/*
 * Markdown rendering pulls in the whole react-markdown stack (~250 kB). It is
 * lazy-loaded so the ChatPage chunk stays lean; the stack only downloads when
 * the first message with content actually renders.
 */
const MarkdownRenderer = lazy(() =>
  import("./MarkdownRenderer").then((m) => ({ default: m.MarkdownRenderer }))
);

const MarkdownFallback: React.FC = () => (
  <div className="flex flex-col gap-2 py-1" aria-hidden>
    <div className="h-3 w-3/4 rounded bg-[var(--bg-tertiary)] skeleton-shimmer" />
    <div className="h-3 w-1/2 rounded bg-[var(--bg-tertiary)] skeleton-shimmer" />
  </div>
);

interface ChatMessageProps {
  message: ChatMessageType;
  onRetry?: () => void;
  onReact?: (messageId: string, reaction: "up" | "down" | "flag") => void;
}

/* Shared icon-button style used in action bar */
const actionBtn =
  "p-1.5 rounded-[var(--radius-md)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors cursor-pointer";

const ChatMessageComponent: React.FC<ChatMessageProps> = ({ message, onRetry, onReact }) => {
  const [copied, setCopied]           = useState(false);
  const [showActions, setShowActions] = useState(false);
  const contentRef                    = useRef<HTMLDivElement>(null);
  const isUser                        = message.role === "user";

  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const messageTime    = message.created_at ? new Date(message.created_at) : new Date();
  const formattedTime  = messageTime.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const fullTime       = messageTime.toLocaleString();

  /* ── User message ── */
  if (isUser) {
    return (
      <TooltipProvider>
        <div
          ref={contentRef}
          className="flex w-full py-[calc(var(--space-factor,1)*16px)] group justify-center bg-transparent select-none"
          role="article"
          aria-label="User message"
        >
          <div className="w-full max-w-[780px] flex justify-end px-3 sm:px-6">
            <div className="flex flex-col items-end gap-1.5 max-w-[90%] sm:max-w-[75%]">
              {/* Bubble */}
              <div className="px-3.5 py-2.5 sm:px-4 sm:py-3 rounded-[var(--radius-md)] bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-[14px] sm:text-[15px] leading-relaxed select-text">
                {message.content && (
                  <Suspense fallback={<MarkdownFallback />}>
                    <MarkdownRenderer content={message.content} />
                  </Suspense>
                )}
              </div>
              {/* Timestamp */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="text-[11px] text-[var(--text-muted)] mr-1.5 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity cursor-default">
                    {formattedTime}
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top" align="center">{fullTime}</TooltipContent>
              </Tooltip>
            </div>
          </div>
        </div>
      </TooltipProvider>
    );
  }

  /* ── Assistant message ── */
  return (
    <TooltipProvider>
      <div
        ref={contentRef}
        className="flex w-full py-[calc(var(--space-factor,1)*16px)] sm:py-[calc(var(--space-factor,1)*24px)] group bg-transparent justify-center transition-colors select-none"
        role="article"
        aria-label="Assistant response"
        onMouseEnter={() => setShowActions(true)}
        onMouseLeave={() => setShowActions(false)}
      >
        <div className="w-full max-w-[780px] flex gap-2.5 sm:gap-4 px-3 sm:px-6 items-start">
          {/* Avatar */}
          <Avatar className="w-8 h-8 flex-shrink-0 bg-[var(--bg-tertiary)] border border-[var(--border-default)]">
            <AvatarFallback className="bg-transparent">
              <Sparkles size={14} className="text-[var(--text-secondary)]" />
            </AvatarFallback>
          </Avatar>

          {/* Content */}
          <div className="flex-1 flex flex-col gap-2.5 min-w-0">
            {/* Tool calls */}
            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="flex flex-col gap-1.5 w-full">
                {message.toolCalls.map((tc) => (
                  <ToolCallCard key={tc.id} toolCall={tc} />
                ))}
              </div>
            )}

            {/* Markdown content */}
            <div
              className="flex flex-col gap-1.5 select-text text-[var(--text-primary)] text-[15px] leading-[1.65]"
            >
              {message.content ? (
                <Suspense fallback={<MarkdownFallback />}>
                  <MarkdownRenderer content={message.content} />
                </Suspense>
              ) : message.status === "pending" ? (
                /* Typing indicator */
                <div className="flex items-center gap-1.5 text-[var(--text-muted)] text-xs py-2">
                  {[0, 150, 300].map((delay) => (
                    <span
                      key={delay}
                      className="h-1.5 w-1.5 rounded-full bg-[var(--text-muted)] animate-bounce"
                      style={{ animationDelay: `${delay}ms` }}
                    />
                  ))}
                </div>
              ) : message.status === "failed" && message.error ? (
                /* Error state */
                <div className="bg-red-500/10 border border-red-500/20 rounded-[var(--radius-xl)] p-3 text-xs flex flex-col gap-1 max-w-xl animate-fade-in">
                  <span className="font-semibold text-red-400 flex items-center gap-1.5">
                    ⚠ Generation failed
                  </span>
                  <span className="text-[var(--text-muted)] leading-normal">{message.error}</span>
                </div>
              ) : null}

              {message.status === "streaming" && <StreamingCursor />}

              {message.status === "interrupted" && (
                <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] mt-1 animate-fade-in">
                  <span className="h-1 w-1 rounded-full bg-[var(--text-muted)] flex-shrink-0" />
                  <span>Generation stopped — response is incomplete.</span>
                </div>
              )}
            </div>

            {/* General-knowledge hint: retrieval was skipped because the user
                has no uploaded documents. Only shown while the answer streams
                or once completed — a failed/interrupted reply must not claim
                it was answered from general knowledge. */}
            {message.retrievalSkipped &&
              (message.status === "streaming" || message.status === "completed") && (
                <div className="flex items-center gap-1.5 w-fit rounded-full border border-[var(--border-default)] bg-[var(--bg-tertiary)] px-2.5 py-1 text-[11px] text-[var(--text-muted)] mt-1 select-text animate-fade-in">
                  <FileQuestion size={12} className="flex-shrink-0 text-[var(--text-secondary)]" />
                  <span>Answering from general knowledge — attach files here or use @documents for your library</span>
                </div>
              )}

            {/* Citations */}
            {message.citations && message.citations.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-1 select-text">
                {message.citations.map((c, idx) => (
                  <CitationCard key={c.chunk_id || idx} citation={c} index={idx} />
                ))}
              </div>
            )}

            {/* Action bar */}
            <div
              className={cn(
                "flex items-center justify-between gap-2 mt-2 pt-1 border-t border-transparent transition-opacity duration-200",
                showActions ? "opacity-100" : "opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
              )}
            >
              {/* Left: timestamp + reactions */}
              <div className="flex items-center gap-0.5">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button className="flex items-center gap-1 px-1.5 py-1 text-[10px] text-[var(--text-muted)] cursor-default rounded-[var(--radius-sm)] hover:bg-[var(--bg-tertiary)] transition-colors mr-1">
                      <Clock size={10} className="opacity-60" />
                      {formattedTime}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" align="center">{fullTime}</TooltipContent>
                </Tooltip>

                {message.status !== "streaming" && (
                  <>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => onReact?.(message.id || "", "up")}
                          className={cn(actionBtn, "hover:text-emerald-400")}
                          aria-label="Helpful"
                        >
                          <ThumbsUp size={11} />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top">Helpful</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => onReact?.(message.id || "", "down")}
                          className={cn(actionBtn, "hover:text-red-400")}
                          aria-label="Not helpful"
                        >
                          <ThumbsDown size={11} />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top">Not helpful</TooltipContent>
                    </Tooltip>
                  </>
                )}
              </div>

              {/* Right: copy, flag, retry */}
              <div className="flex items-center gap-0.5">
                {message.content && message.status !== "streaming" && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={handleCopy}
                        className={cn(actionBtn, copied && "text-emerald-400")}
                        aria-label={copied ? "Copied" : "Copy response"}
                      >
                        {copied ? (
                          <span className="flex items-center gap-1">
                            <Check size={11} />
                            <span className="text-[10px]">Copied</span>
                          </span>
                        ) : (
                          <Copy size={11} />
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">{copied ? "Copied!" : "Copy response"}</TooltipContent>
                  </Tooltip>
                )}

                {message.status !== "streaming" && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => onReact?.(message.id || "", "flag")}
                        className={cn(actionBtn, "hover:text-amber-400")}
                        aria-label="Report issue"
                      >
                        <Flag size={11} />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">Report issue</TooltipContent>
                  </Tooltip>
                )}

                {(message.status === "failed" || message.status === "interrupted") && onRetry && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={onRetry}
                        className={cn(
                          "flex items-center gap-1 px-2 py-1 rounded-[var(--radius-md)] transition-colors text-[10px] font-medium cursor-pointer",
                          message.status === "failed"
                            ? "text-red-400 hover:bg-red-500/10"
                            : "text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]"
                        )}
                        aria-label="Retry query"
                      >
                        <RefreshCw size={11} />
                        Retry
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">Retry query</TooltipContent>
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

/* Memoized so only the actively-streaming message re-renders per token. */
export const ChatMessage = React.memo(ChatMessageComponent);

export default ChatMessage;
