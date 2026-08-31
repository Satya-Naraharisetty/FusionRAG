import React, { useState, useRef, useEffect } from "react";
import {
  Copy,
  Check,
  RefreshCw,
  Clock,
  ThumbsUp,
  ThumbsDown,
  Flag,
  Sparkles,
  FileQuestion,
  Pencil,
  Volume2,
  VolumeX,
  RotateCcw,
  Brain,
  ChevronDown,
} from "lucide-react";
import { ChatMessage as ChatMessageType, Citation } from "../../types";
import { CitationCard } from "./CitationCard";
import { ToolCallCard } from "./ToolCallCard";
import { StreamingCursor } from "./StreamingCursor";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { Avatar, AvatarFallback } from "../ui/Avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";

interface ChatMessageProps {
  message: ChatMessageType;
  onRetry?: () => void;
  onReact?: (messageId: string, reaction: "up" | "down" | "flag") => void;
  onEditPrompt?: (messageId: string, newText: string) => void;
  onRegenerate?: (messageId: string) => void;
  onSelectCitation?: (citation: Citation) => void;
}

/* Shared icon-button style used in action bar */
const actionBtn =
  "p-1.5 rounded-[var(--radius-md)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors cursor-pointer";

// Helper to parse <think>...</think> tags from content
function parseThinkingContent(rawContent: string): { thinking: string | null; answer: string } {
  if (!rawContent) return { thinking: null, answer: "" };
  const match = /<think>([\s\S]*?)<\/think>/i.exec(rawContent);
  if (match) {
    const thinking = match[1].trim();
    const answer = rawContent.replace(/<think>[\s\S]*?<\/think>/i, "").trim();
    return { thinking, answer };
  }
  return { thinking: null, answer: rawContent };
}

const ChatMessageComponent: React.FC<ChatMessageProps> = ({
  message,
  onRetry,
  onReact,
  onEditPrompt,
  onRegenerate,
  onSelectCitation,
}) => {
  const [copied, setCopied]           = useState(false);
  const [showActions, setShowActions] = useState(false);
  const [isEditing, setIsEditing]     = useState(false);
  const [editText, setEditText]       = useState(message.content || "");
  const [isSpeaking, setIsSpeaking]   = useState(false);
  const contentRef                    = useRef<HTMLDivElement>(null);
  const textareaRef                   = useRef<HTMLTextAreaElement>(null);
  const isUser                        = message.role === "user";

  useEffect(() => {
    setEditText(message.content || "");
  }, [message.content]);

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [isEditing]);

  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSaveEdit = () => {
    if (!editText.trim()) return;
    setIsEditing(false);
    if (editText.trim() !== message.content && onEditPrompt && message.id) {
      onEditPrompt(message.id, editText.trim());
    }
  };

  const handleCancelEdit = () => {
    setEditText(message.content || "");
    setIsEditing(false);
  };

  const handleToggleSpeak = () => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;

    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }

    const { answer } = parseThinkingContent(message.content || "");
    const cleanText = answer.replace(/[#*`_~[\]()]/g, " ").replace(/\s+/g, " ").trim();
    if (!cleanText) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
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
          className="flex w-full py-[calc(var(--space-factor,1)*14px)] group justify-center bg-transparent select-none"
          role="article"
          aria-label="User message"
          onMouseEnter={() => setShowActions(true)}
          onMouseLeave={() => setShowActions(false)}
        >
          <div className="w-full max-w-[860px] flex justify-end px-3 sm:px-6">
            <div className="flex flex-col items-end gap-1.5 max-w-[90%] sm:max-w-[80%] w-full">
              {isEditing ? (
                /* Inline Edit Box */
                <div className="w-full flex flex-col gap-2 p-3 rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)] border border-[var(--border-hover)] shadow-lg animate-fade-in">
                  <textarea
                    ref={textareaRef}
                    value={editText}
                    onChange={(e) => {
                      setEditText(e.target.value);
                      e.target.style.height = "auto";
                      e.target.style.height = `${e.target.scrollHeight}px`;
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSaveEdit();
                      } else if (e.key === "Escape") {
                        handleCancelEdit();
                      }
                    }}
                    className="w-full min-h-[60px] bg-transparent text-[14px] sm:text-[15px] text-[var(--text-primary)] placeholder-[var(--text-muted)] resize-none outline-none leading-relaxed select-text"
                    placeholder="Edit prompt..."
                  />
                  <div className="flex items-center justify-end gap-2 pt-1 border-t border-[var(--border-subtle)]">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleCancelEdit}
                      className="text-xs h-7 px-2.5 text-[var(--text-muted)]"
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="default"
                      size="sm"
                      onClick={handleSaveEdit}
                      disabled={!editText.trim()}
                      className="text-xs h-7 px-3"
                    >
                      Save & Submit
                    </Button>
                  </div>
                </div>
              ) : (
                /* Normal Bubble */
                <div className="flex items-center gap-1.5 group/bubble">
                  {/* Edit action button */}
                  {onEditPrompt && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => setIsEditing(true)}
                          className={cn(
                            actionBtn,
                            "opacity-0 group-hover/bubble:opacity-100 sm:group-hover:opacity-100 transition-opacity",
                            showActions && "opacity-100"
                          )}
                          aria-label="Edit message"
                        >
                          <Pencil size={12} />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="left">Edit prompt</TooltipContent>
                    </Tooltip>
                  )}

                  <div className="px-3.5 py-2.5 sm:px-4 sm:py-3 rounded-[var(--radius-md)] bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-[14px] sm:text-[15px] leading-relaxed select-text shadow-xs">
                    {message.content && <MarkdownRenderer content={message.content} />}
                  </div>
                </div>
              )}

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
  const { thinking, answer } = parseThinkingContent(message.content || "");

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
        <div className="w-full max-w-[860px] flex gap-2.5 sm:gap-4 px-3 sm:px-6 items-start">
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

            {/* Thinking / Reasoning Accordion */}
            {thinking && (
              <details className="group/think rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/30 text-xs overflow-hidden transition-all duration-200">
                <summary className="flex cursor-pointer items-center gap-2 px-3.5 py-2 text-[12px] font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]/50 select-none transition-colors">
                  <Brain size={13} className="text-[var(--accent-primary)]" />
                  <span>Thought Process</span>
                  <ChevronDown size={13} className="ml-auto transition-transform duration-200 group-open/think:rotate-180 text-[var(--text-muted)]" />
                </summary>
                <div className="px-3.5 pb-3 pt-2 border-t border-[var(--border-subtle)] text-[12px] text-[var(--text-muted)] font-mono leading-relaxed whitespace-pre-wrap bg-[var(--bg-secondary)]/40">
                  {thinking}
                </div>
              </details>
            )}

            {/* Markdown content */}
            <div
              className="flex flex-col gap-1.5 select-text text-[var(--text-primary)] text-[15px] leading-[1.65]"
            >
              {answer ? (
                <MarkdownRenderer content={answer} />
              ) : message.status === "pending" || (message.status === "streaming" && !answer) ? (
                /* Typing indicator */
                <div className="flex items-center gap-2 text-[var(--text-muted)] text-xs py-2 animate-fade-in">
                  <div className="flex items-center gap-1.5">
                    {[0, 150, 300].map((delay) => (
                      <span
                        key={delay}
                        className="h-1.5 w-1.5 rounded-full bg-[var(--accent-primary)] animate-bounce"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </div>
                  <span className="text-[12px] font-mono text-[var(--text-secondary)] opacity-90 pl-1">
                    Analyzing documents and generating response...
                  </span>
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

            {/* General-knowledge hint */}
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
                  <CitationCard
                    key={c.chunk_id || idx}
                    citation={c}
                    index={idx}
                    onSelect={onSelectCitation}
                  />
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
              {/* Left: timestamp + reactions + read aloud */}
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

                    {/* Read Aloud (TTS) */}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={handleToggleSpeak}
                          className={cn(
                            actionBtn,
                            isSpeaking && "text-[var(--accent-primary)] bg-[var(--accent-primary)]/10"
                          )}
                          aria-label={isSpeaking ? "Stop reading" : "Read aloud"}
                        >
                          {isSpeaking ? <VolumeX size={11} /> : <Volume2 size={11} />}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top">{isSpeaking ? "Stop speech" : "Read aloud"}</TooltipContent>
                    </Tooltip>
                  </>
                )}
              </div>

              {/* Right: copy, regenerate, flag, retry */}
              <div className="flex items-center gap-0.5">
                {/* One-click Regenerate */}
                {message.status === "completed" && onRegenerate && message.id && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => onRegenerate(message.id!)}
                        className={cn(actionBtn, "hover:text-[var(--accent-primary)]")}
                        aria-label="Regenerate response"
                      >
                        <RotateCcw size={11} />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">Regenerate response</TooltipContent>
                  </Tooltip>
                )}

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

