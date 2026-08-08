import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { Square, AlertCircle, Paperclip, Mic, X, ArrowUp, Image, FileText } from "lucide-react";
import { Button } from "../ui/Button";
import { useDraft } from "../../hooks/useDrafts";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from "../ui/command";
import { cn } from "../../lib/utils";

interface ChatInputProps {
  conversationId: string | null;
  onSend: (text: string, attachments?: File[]) => void;
  onStop: () => void;
  isStreaming: boolean;
  onVoiceInput?: () => void;
}

const SLASH_COMMANDS = [
  { id: "search", label: "Search documents", description: "Query your knowledge base", icon: "🔍", shortcut: "/search" },
  { id: "summarize", label: "Summarize", description: "Summarize selected documents", icon: "📄", shortcut: "/summarize" },
  { id: "explain", label: "Explain concept", description: "Get detailed explanation", icon: "💡", shortcut: "/explain" },
  { id: "compare", label: "Compare", description: "Compare two documents", icon: "⚖️", shortcut: "/compare" },
  { id: "code", label: "Code helper", description: "Generate or explain code", icon: "💻", shortcut: "/code" },
  { id: "settings", label: "Settings", description: "Open settings panel", icon: "⚙️", shortcut: "/settings" },
];

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_TYPES = ["application/pdf", "text/plain", "text/markdown", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];

export const ChatInput: React.FC<ChatInputProps> = ({
  conversationId,
  onSend,
  onStop,
  isStreaming,
  onVoiceInput,
}) => {
  const { draft, setDraft, clearDraft } = useDraft(conversationId);
  const { isOnline } = useOnlineStatus();
  const [text, setText] = useState(draft);
  const [showCommands, setShowCommands] = useState(false);
  const [commandSearch, setCommandSearch] = useState("");
  const [attachments, setAttachments] = useState<File[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [charCount, setCharCount] = useState(0);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setText(draft);
  }, [conversationId, draft]);

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const newHeight = Math.min(textarea.scrollHeight, 200);
    textarea.style.height = `${newHeight}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
    setCharCount(text.length);
  }, [text, adjustHeight]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);
    setDraft(val);
    adjustHeight();
  };

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || isStreaming || !isOnline) return;

    if (attachments.length > 0) {
      onSend(trimmed, attachments);
    } else {
      onSend(trimmed);
    }
    setText("");
    setAttachments([]);
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
    if (e.key === "/" && text === "" && !e.shiftKey) {
      e.preventDefault();
      setShowCommands(true);
      setCommandSearch("");
    }
    if (e.key === "Escape") {
      setShowCommands(false);
    }
  };

  const handleFileSelect = (files: FileList | null) => {
    if (!files) return;
    const newFiles = Array.from(files).filter((file) => {
      if (file.size > MAX_FILE_SIZE) {
        alert(`File ${file.name} exceeds 10MB limit`);
        return false;
      }
      if (!ALLOWED_TYPES.includes(file.type)) {
        alert(`File ${file.name} type not supported`);
        return false;
      }
      return true;
    });
    setAttachments((prev) => [...prev, ...newFiles].slice(0, 5));
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleCommandSelect = (cmd: typeof SLASH_COMMANDS[0]) => {
    setText(cmd.shortcut + " ");
    setShowCommands(false);
    textareaRef.current?.focus();
  };

  const filteredCommands = useMemo(() => {
    if (!commandSearch) return SLASH_COMMANDS;
    return SLASH_COMMANDS.filter(
      (c) => c.label.toLowerCase().includes(commandSearch.toLowerCase()) ||
             c.description.toLowerCase().includes(commandSearch.toLowerCase())
    );
  }, [commandSearch]);

  const isNearingLimit = charCount > 3000;
  const isOverLimit = charCount > 4000;
  const hasContent = text.trim().length > 0 || attachments.length > 0;

  return (
    <form onSubmit={handleSubmit} className="relative w-full max-w-3xl px-4 select-none">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ALLOWED_TYPES.join(",")}
        onChange={(e) => handleFileSelect(e.target.files)}
        className="hidden"
        id="chat-file-input"
      />

      <div className="relative flex flex-col gap-2">
        {/* Warning Alert */}
        {!isOnline && (
          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-red-500 bg-red-50 dark:bg-red-950/15 p-2 rounded-xl border border-red-200/50 dark:border-red-900/10 animate-slide-down">
            <AlertCircle size={12} />
            <span>Sending disabled. You are offline.</span>
          </div>
        )}

        {/* Attachments Preview Tray */}
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1 animate-slide-down">
            {attachments.map((file, idx) => (
              <div key={idx} className="flex items-center gap-2 px-3 py-1.5 bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700/60 rounded-xl animate-fade-in">
                <div className="flex items-center gap-1.5 text-xs text-zinc-700 dark:text-zinc-300">
                  {file.type.startsWith("image/") ? <Image size={13} /> : <FileText size={13} />}
                  <span className="truncate max-w-[140px] font-medium">{file.name}</span>
                  <span className="text-[10px] text-zinc-500">({(file.size / 1024).toFixed(0)} KB)</span>
                </div>
                <button
                  type="button"
                  onClick={() => removeAttachment(idx)}
                  className="p-0.5 text-zinc-400 hover:text-red-500 dark:hover:text-red-400 rounded transition-colors"
                  aria-label={`Remove ${file.name}`}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input Wrapper Card - Matches ChatGPT's modern input container */}
        <div className={cn(
          "relative flex items-end border transition-all duration-200 rounded-[22px] bg-zinc-100/50 dark:bg-[var(--bg-input,#2A2A2A)] text-zinc-900 dark:text-zinc-100",
          "border-zinc-200/60 dark:border-[var(--border-color)] focus-within:border-zinc-300 dark:focus-within:border-zinc-750 focus-within:shadow-[0_8px_30px_rgba(0,0,0,0.15)]",
          isRecording && "border-red-500/50 dark:border-red-900/30"
        )}>
          {/* Paperclip upload button */}
          <div className="flex items-center justify-center pl-3 pr-1 h-12">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming || attachments.length >= 5}
              className="h-8 w-8 text-zinc-550 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-800/60 rounded-full transition-colors flex items-center justify-center cursor-pointer"
              aria-label="Attach files"
            >
              <Paperclip size={16} />
            </Button>
          </div>

          <div className="flex-1 flex flex-col min-w-0">
            <textarea
              ref={textareaRef}
              value={text}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={isStreaming ? "AI is responding..." : "Message Hybrid RAG..."}
              rows={1}
              disabled={!isOnline || isStreaming}
              className={cn(
                "flex-1 max-h-[200px] min-h-[44px] bg-transparent border-0 text-zinc-800 dark:text-zinc-100 text-xs sm:text-[13px] px-2 py-3 resize-none focus:outline-none disabled:opacity-50 placeholder:text-zinc-400 dark:placeholder:text-zinc-500 leading-relaxed scrollbar-none",
                attachments.length > 0 && "pb-2"
              )}
              style={{ outline: "none", boxShadow: "none" }}
              aria-label="Message prompt input"
            />

            {showCommands && (
              <Command className="absolute bottom-full left-0 right-0 mb-2 bg-[var(--bg-secondary,#171717)] border border-[var(--border-color)] rounded-2xl shadow-xl overflow-hidden animate-slide-up z-10 text-zinc-300">
                <CommandInput
                  value={commandSearch}
                  onValueChange={setCommandSearch}
                  placeholder="Search commands..."
                  className="h-10 px-4 bg-transparent border-0 text-zinc-100 text-xs placeholder:text-zinc-500 focus-visible:ring-0 focus:outline-none"
                  autoFocus
                />
                <CommandEmpty className="py-6 text-center text-zinc-500 text-xs">No commands found.</CommandEmpty>
                <CommandGroup>
                  {filteredCommands.map((cmd) => (
                    <CommandItem
                      key={cmd.id}
                      onSelect={() => handleCommandSelect(cmd)}
                      className="flex items-center gap-3 px-4 py-2.5 text-xs hover:bg-zinc-900/50 cursor-pointer"
                    >
                      <span className="text-sm">{cmd.icon}</span>
                      <div className="flex-1 text-left">
                        <div className="font-medium text-zinc-100">{cmd.label}</div>
                        <div className="text-[10px] text-zinc-500">{cmd.description}</div>
                      </div>
                      <kbd className="px-1.5 py-0.5 text-[9px] font-mono bg-zinc-800 text-zinc-400 rounded">{cmd.shortcut}</kbd>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </Command>
            )}
          </div>

          {/* Right Action buttons: Voice & Send */}
          <div className="flex items-center gap-1.5 h-12 pr-3 pl-1">
            {/* Voice Input */}
            {onVoiceInput && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => { onVoiceInput(); setIsRecording(!isRecording); }}
                disabled={isStreaming}
                className={cn(
                  "h-8 w-8 rounded-full transition-all flex items-center justify-center cursor-pointer",
                  isRecording
                    ? "text-zinc-100 bg-red-500 animate-pulse"
                    : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-850"
                )}
                aria-label={isRecording ? "Stop recording" : "Record voice"}
                aria-pressed={isRecording}
              >
                <Mic size={15} />
              </Button>
            )}

            {/* Circle Send / Stop Button - Matches ChatGPT's modern arrow-up design */}
            {isStreaming ? (
              <Button
                type="button"
                onClick={onStop}
                size="icon"
                className="h-8 w-8 bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-white dark:text-zinc-950 rounded-full flex items-center justify-center shadow-xs cursor-pointer transition-transform active:scale-95 duration-200"
                aria-label="Stop generation"
              >
                <Square size={9} fill="currentColor" />
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={!hasContent || !isOnline}
                size="icon"
                className={cn(
                  "h-8 w-8 rounded-full flex items-center justify-center shadow-xs transition-all active:scale-95 duration-200 cursor-pointer",
                  hasContent && isOnline
                    ? "bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-zinc-150 dark:text-zinc-950 dark:hover:bg-zinc-200"
                    : "bg-zinc-200 dark:bg-zinc-800/80 text-zinc-400 dark:text-zinc-500 cursor-not-allowed border-0"
                )}
                aria-label="Send query"
              >
                <ArrowUp size={15} strokeWidth={3} />
              </Button>
            )}
          </div>
        </div>

        {/* Character count limit warning indicator */}
        {(isNearingLimit || attachments.length > 0) && (
          <div className={cn(
            "text-[9px] font-mono text-right self-end px-2 transition-colors",
            isOverLimit ? "text-red-500 font-bold" : "text-zinc-500"
          )}>
            {charCount} / 4000 {attachments.length > 0 && `· ${attachments.length} files`}
          </div>
        )}
      </div>
    </form>
  );
};