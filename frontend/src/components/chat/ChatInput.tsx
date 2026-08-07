import React, { useEffect, useRef, useState } from "react";
import { Square, AlertCircle, ArrowUp } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { useDraft } from "../../hooks/useDrafts";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";

interface ChatInputProps {
  conversationId: string | null;
  onSend: (text: string) => void;
  onStop: () => void;
  isStreaming: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  conversationId,
  onSend,
  onStop,
  isStreaming,
}) => {
  const { draft, setDraft, clearDraft } = useDraft(conversationId);
  const { isOnline } = useOnlineStatus();
  const [text, setText] = useState(draft);

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Sync draft when conversation switches
  useEffect(() => {
    setText(draft);
  }, [conversationId, draft]);

  // Sync text to draft on change
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);
    setDraft(val);
    adjustHeight();
  };

  const adjustHeight = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  };

  useEffect(() => {
    adjustHeight();
  }, [text]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || isStreaming || !isOnline) return;

    onSend(trimmed);
    setText("");
    clearDraft();
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isNearingLimit = text.length > 1000;
  const isOverLimit = text.length > 4000;

  return (
    <form
      onSubmit={handleSubmit}
      className="p-4 bg-gradient-to-t from-zinc-950 via-zinc-950/90 to-transparent relative border-t-0"
    >
      <div className="max-w-3xl mx-auto relative flex flex-col gap-2">
        {/* Warning messages */}
        {!isOnline && (
          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-red-400 bg-red-950/15 p-2 rounded-lg border border-red-900/10">
            <AlertCircle size={12} />
            <span>Sending disabled. You are offline.</span>
          </div>
        )}

        <div className="relative flex items-end bg-zinc-900/40 backdrop-blur-md border border-zinc-800/80 focus-within:border-violet-500/40 focus-within:shadow-[0_0_15px_rgba(139,92,246,0.15)] rounded-2xl overflow-hidden transition-all duration-300">
          <Textarea
            ref={textareaRef}
            value={text}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything... (Enter to send, Shift+Enter for new line)"
            rows={1}
            disabled={!isOnline}
            className="flex-1 max-h-[200px] min-h-[44px] bg-transparent border-0 text-zinc-150 text-xs px-4 py-3.5 resize-none focus-visible:ring-0 focus-visible:ring-offset-0 disabled:opacity-50 placeholder:text-zinc-500 leading-relaxed scrollbar-none"
            aria-label="Chat input query"
          />
          
          <div className="flex items-center h-12 px-3">
            {isStreaming ? (
              <Button
                type="button"
                onClick={onStop}
                className="h-8 w-8 bg-zinc-800 hover:bg-zinc-700 text-zinc-150 rounded-full flex items-center justify-center shadow-md cursor-pointer transition-transform active:scale-95 duration-200"
                aria-label="Stop generation"
              >
                <Square size={10} fill="currentColor" />
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={!text.trim() || !isOnline}
                className="h-8 w-8 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:opacity-90 disabled:opacity-30 disabled:from-zinc-800 disabled:to-zinc-800 text-white disabled:text-zinc-500 rounded-full flex items-center justify-center shadow-md cursor-pointer transition-all active:scale-95 duration-200"
                aria-label="Send message"
              >
                <ArrowUp size={16} strokeWidth={2.5} />
              </Button>
            )}
          </div>
        </div>

        {/* Character counts */}
        {isNearingLimit && (
          <div
            className={`text-[9px] font-mono text-right self-end ${
              isOverLimit ? "text-red-500 font-bold" : "text-zinc-500"
            }`}
          >
            {text.length} / 4000
          </div>
        )}
      </div>
    </form>
  );
};
