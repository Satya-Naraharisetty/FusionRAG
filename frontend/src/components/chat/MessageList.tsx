import React, { useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import { ChatMessage } from "../../types";
import { ChatBubble } from "./ChatBubble";
import { Button } from "../ui/button";

interface MessageListProps {
  messages: ChatMessage[];
  onRetry: () => void;
  isStreaming: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  onRetry,
  isStreaming,
}) => {
  const listRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  const handleScroll = () => {
    const container = listRef.current;
    if (!container) return;

    const threshold = 150;
    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < threshold;

    setShowScrollBtn(!isAtBottom);
  };

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isStreaming) {
      scrollToBottom();
    }
  }, [messages, isStreaming]);

  useEffect(() => {
    // Scroll to bottom on initial load
    scrollToBottom();
  }, []);

  return (
    <div className="flex-1 w-full overflow-hidden relative flex flex-col">
      {/* Scrollable Container */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent flex flex-col"
      >
        <div className="flex-1 flex flex-col">
          {messages.map((msg, idx) => (
            <ChatBubble
              key={msg.id || idx}
              message={msg}
              onRetry={idx === messages.length - 1 ? onRetry : undefined}
            />
          ))}
          <div ref={bottomRef} className="h-4 flex-shrink-0" />
        </div>
      </div>

      {/* Floating Scroll Button */}
      {showScrollBtn && (
        <Button
          onClick={scrollToBottom}
          size="icon"
          className="absolute bottom-4 right-4 h-9 w-9 bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-300 hover:text-zinc-150 rounded-full shadow-lg z-10 cursor-pointer animate-bounce"
          aria-label="Scroll to bottom"
        >
          <ArrowDown size={16} />
        </Button>
      )}
    </div>
  );
};
