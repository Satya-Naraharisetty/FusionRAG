import React, { useEffect, useRef, useState, useCallback } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChatMessage as ChatMessageType } from "../../types";
import { ChatMessage } from "./ChatMessage";
import { Button } from "../ui/Button";

interface MessageListProps {
  messages: ChatMessageType[];
  onRetry: () => void;
  isStreaming: boolean;
}

const MESSAGE_HEIGHT_ESTIMATE = 180;
const OVERSAM = 5;

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  onRetry,
  isStreaming,
}) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [scrollDirection, setScrollDirection] = useState<"up" | "down">("down");
  const lastScrollTop = useRef(0);
  const isUserScrolling = useRef(false);
  const scrollTimeoutRef = useRef<NodeJS.Timeout>();

  const scrollToBottom = useCallback((smooth = true) => {
    bottomRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto" });
  }, []);

  const handleScroll = useCallback(() => {
    const container = parentRef.current;
    if (!container) return;

    const scrollTop = container.scrollTop;
    const scrollHeight = container.scrollHeight;
    const clientHeight = container.clientHeight;

    const threshold = 100;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < threshold;
    setShowScrollBtn(!isAtBottom);

    if (scrollTop > lastScrollTop.current) {
      setScrollDirection("down");
    } else if (scrollTop < lastScrollTop.current) {
      setScrollDirection("up");
    }
    lastScrollTop.current = scrollTop;

    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    scrollTimeoutRef.current = setTimeout(() => {
      isUserScrolling.current = false;
    }, 150);
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (e.deltaY !== 0) {
      isUserScrolling.current = true;
    }
  }, []);

  const handleTouchStart = useCallback(() => {
    isUserScrolling.current = true;
  }, []);

  useEffect(() => {
    if (isStreaming && !isUserScrolling.current) {
      scrollToBottom();
    }
  }, [messages, isStreaming, scrollToBottom]);

  useEffect(() => {
    scrollToBottom(false);
  }, [scrollToBottom]);

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => MESSAGE_HEIGHT_ESTIMATE,
    overscan: OVERSAM,
  });

  const virtualItems = virtualizer.getVirtualItems();

  const handleScrollBtnClick = () => {
    isUserScrolling.current = false;
    scrollToBottom();
  };

  return (
    <div className="flex-1 w-full overflow-hidden relative flex flex-col">
      <div
        ref={parentRef}
        onScroll={handleScroll}
        onWheel={handleWheel}
        onTouchStart={handleTouchStart}
        className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent flex flex-col"
        style={{ contain: "layout paint" }}
        role="log"
        aria-live="polite"
      >
        <div
          style={{
            height: virtualizer.getTotalSize(),
            width: "100%",
            position: "relative",
            contain: "layout paint",
          }}
          className="flex flex-col"
        >
          {virtualItems.map((virtualItem) => {
            const msg = messages[virtualItem.index];
            if (!msg) return null;
            const isLast = virtualItem.index === messages.length - 1;

            return (
              <div
                key={msg.id}
                ref={virtualizer.measureElement}
                data-index={virtualItem.index}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${virtualItem.start}px)`,
                  contain: "layout paint",
                }}
              >
                <ChatMessage
                  message={msg}
                  onRetry={isLast ? onRetry : undefined}
                />
              </div>
            );
          })}
        </div>
        {/* Scroll anchor spacer positioned outside the absolute virtual container */}
        <div ref={bottomRef} className="h-36 w-full flex-shrink-0" />
      </div>

      {showScrollBtn && (
        <Button
          onClick={handleScrollBtnClick}
          size="icon"
          className="absolute bottom-4 right-4 z-10 h-10 w-10 cursor-pointer rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/90 text-[var(--text-secondary)] shadow-lg backdrop-blur-sm transition-all duration-300 ease-emphasized hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          aria-label={scrollDirection === "down" ? "Scroll to bottom" : "Scroll to top"}
        >
          {scrollDirection === "down" ? (
            <ArrowDown size={18} className="animate-bounce" />
          ) : (
            <ArrowUp size={18} />
          )}
        </Button>
      )}

      {isStreaming && !showScrollBtn && (
        <div className="absolute bottom-4 right-4 z-10 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent-primary)]/15 text-[var(--accent-primary)] animate-pulse" aria-live="polite" aria-atomic="true">
          <span className="text-xs font-mono">AI</span>
        </div>
      )}
    </div>
  );
};