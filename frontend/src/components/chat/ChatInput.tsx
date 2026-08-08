import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { Square, AlertCircle, Paperclip, Mic, X, Send, Image, FileText, Mic2, Loader2 } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
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
    <form onSubmit={handleSubmit} className="relative w-full max-w-3xl px-4 md:px-6">
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
        {/* Warning messages */}
        {!isOnline && (
          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-red-400 bg-red-950/15 p-2 rounded-lg border border-red-900/10 animate-slide-down">
            <AlertCircle size={12} />
            <span>Sending disabled. You are offline.</span>
          </div>
        )}

        {/* Attachments Preview */}
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1 animate-slide-down">
            {attachments.map((file, idx) => (
              <div key={idx} className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900/50 border border-zinc-800 rounded-lg animate-fade-in">
                <div className="flex items-center gap-1.5 text-xs text-zinc-300">
                  {file.type.startsWith("image/") ? <Image size={13} /> : file.type === "application/pdf" ? <FileText size={13} /> : <Paperclip size={13} />}
                  <span className="truncate max-w-[150px] font-medium">{file.name}</span>
                  <span className="text-zinc-500">({(file.size / 1024).toFixed(1)} KB)</span>
                </div>
                <button
                  type="button"
                  onClick={() => removeAttachment(idx)}
                  className="p-0.5 text-zinc-500 hover:text-red-400 hover:bg-red-950/20 rounded transition-colors"
                  aria-label={`Remove ${file.name}`}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input Area */}
        <div className={cn(
          "relative flex items-end bg-zinc-900/40 backdrop-blur-md border rounded-2xl overflow-hidden transition-all duration-300 ease-standard",
          "border-zinc-800/80",
          "focus-within:border-violet-500/40 focus-within:shadow-[0_0_15px_rgba(139,92,246,0.15)]",
          isRecording && "border-violet-500/50 bg-violet-950/5 shadow-[0_0_20px_rgba(139,92,246,0.2)]",
          hasContent && "ring-1 ring-violet-500/10"
        )}>
          <div className="flex-1 flex flex-col min-w-0">
            <Textarea
              ref={textareaRef}
              value={text}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={isStreaming ? "AI is responding..." : "Ask anything... (Enter to send, Shift+Enter for new line, / for commands)"}
              rows={1}
              disabled={!isOnline || isStreaming}
              className={cn(
                "flex-1 max-h-[200px] min-h-[44px] bg-transparent border-0 text-zinc-150 text-xs px-4 py-3.5 resize-none focus-visible:ring-0 focus-visible:ring-offset-0 disabled:opacity-50 placeholder:text-zinc-500 leading-relaxed scrollbar-none",
                attachments.length > 0 && "pb-2"
              )}
              aria-label="Chat input query"
            />

            {showCommands && (
              <Command className="absolute bottom-full left-0 right-0 mb-1 bg-zinc-950 border border-zinc-800 rounded-xl shadow-elevation-4 overflow-hidden animate-slide-up z-10">
                <CommandInput
                  value={commandSearch}
                  onValueChange={setCommandSearch}
                  placeholder="Search commands..."
                  className="h-10 px-4 bg-transparent border-0 text-zinc-100 text-xs placeholder:text-zinc-500 focus-visible:ring-0"
                  autoFocus
                />
                <CommandEmpty className="py-6 text-center text-zinc-500 text-xs">No commands found.</CommandEmpty>
                <CommandGroup>
                  {filteredCommands.map((cmd) => (
                    <CommandItem
                      key={cmd.id}
                      onSelect={() => handleCommandSelect(cmd)}
                      className="flex items-center gap-3 px-4 py-2.5 text-xs hover:bg-zinc-900/50"
                    >
                      <span className="text-lg">{cmd.icon}</span>
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

          {/* Action Buttons */}
          <div className="flex items-center gap-1 h-12 px-2">
            {/* Attach File */}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming || attachments.length >= 5}
              className="h-9 w-9 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-colors"
              aria-label="Attach file"
            >
              <Paperclip size={16} />
            </Button>

            {/* Voice Input */}
            {onVoiceInput && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => { onVoiceInput(); setIsRecording(!isRecording); }}
                disabled={isStreaming}
                className={cn(
                  "h-9 w-9 transition-all duration-200",
                  isRecording
                    ? "text-violet-400 bg-violet-950/20 animate-pulse shadow-[0_0_10px_rgba(139,92,246,0.4)]"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
                )}
                aria-label={isRecording ? "Stop voice input" : "Start voice input"}
                aria-pressed={isRecording}
              >
                {isRecording ? <Mic2 size={16} fill="currentColor" /> : <Mic size={16} />}
              </Button>
            )}

            {/* Send / Stop */}
            {isStreaming ? (
              <Button
                type="button"
                onClick={onStop}
                size="icon"
                className="h-9 w-9 bg-zinc-800 hover:bg-zinc-700 text-zinc-150 rounded-full flex items-center justify-center shadow-md cursor-pointer transition-transform active:scale-95 duration-200"
                aria-label="Stop generation"
              >
                <Square size={10} fill="currentColor" />
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={!hasContent || !isOnline}
                size="icon"
                className={cn(
                  "h-9 w-9 rounded-full flex items-center justify-center shadow-md cursor-pointer transition-all active:scale-95 duration-200",
                  hasContent && isOnline
                    ? "bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:opacity-90 text-white"
                    : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                )}
                aria-label="Send message"
              >
                <Send size={16} strokeWidth={2.5} />
                {!hasContent && <Loader2 size={14} className="animate-spin" />}
              </Button>
            )}
          </div>
        </div>

        {/* Character count */}
        {(isNearingLimit || attachments.length > 0) && (
          <div className={cn(
            "text-[9px] font-mono text-right self-end px-1 transition-colors",
            isOverLimit ? "text-red-500 font-bold" : "text-zinc-500"
          )}>
            {charCount} / 4000 {attachments.length > 0 && `· ${attachments.length} file(s)`}
          </div>
        )}
      </div>
    </form>
  );
};