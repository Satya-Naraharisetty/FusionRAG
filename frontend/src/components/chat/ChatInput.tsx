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
    <form
      onSubmit={handleSubmit}
      style={{
        width: "100%",
        maxWidth: "780px",
        padding: "0 20px",
      }}
      className="select-none relative"
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ALLOWED_TYPES.join(",")}
        onChange={(e) => handleFileSelect(e.target.files)}
        className="hidden"
        id="chat-file-input"
      />

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {/* Warning Alert */}
        {!isOnline && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              fontWeight: 600,
              color: "#f87171",
              background: "rgba(248,113,113,0.08)",
              padding: "8px 12px",
              borderRadius: "10px",
              border: "1px solid rgba(248,113,113,0.15)",
            }}
          >
            <AlertCircle size={13} />
            <span>Sending disabled — you are offline.</span>
          </div>
        )}

        {/* Attachments Preview Tray */}
        {attachments.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", padding: "0 4px" }}>
            {attachments.map((file, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "6px 12px",
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(255,255,255,0.09)",
                  borderRadius: "10px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", color: "var(--text-secondary, #A3A3A3)" }}>
                  {file.type.startsWith("image/") ? <Image size={13} /> : <FileText size={13} />}
                  <span style={{ maxWidth: "140px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 500 }}>{file.name}</span>
                  <span style={{ fontSize: "11px", color: "var(--text-muted, #737373)" }}>({(file.size / 1024).toFixed(0)} KB)</span>
                </div>
                <button
                  type="button"
                  onClick={() => removeAttachment(idx)}
                  style={{
                    padding: "2px",
                    color: "var(--text-muted, #737373)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: "4px",
                    transition: "color 0.15s",
                  }}
                  className="hover:text-red-400"
                  aria-label={`Remove ${file.name}`}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input Wrapper — Premium composer */}
        <div
          style={{
            position: "relative",
            display: "flex",
            alignItems: "flex-end",
            background: "var(--bg-input, #2A2A2A)",
            border: "1px solid rgba(255,255,255,0.10)",
            borderRadius: "20px",
            boxShadow: "0 4px 20px rgba(0,0,0,0.25)",
            transition: "border-color 0.2s ease, box-shadow 0.2s ease",
          }}
          className={cn(
            "focus-within:border-white/[0.18] focus-within:shadow-[0_8px_32px_rgba(0,0,0,0.35)]",
            isRecording && "border-red-500/40"
          )}
        >
          {/* Paperclip upload button */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", paddingLeft: "12px", paddingRight: "4px", paddingBottom: "10px", paddingTop: "10px" }}>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming || attachments.length >= 5}
              style={{
                width: "38px",
                height: "38px",
                borderRadius: "50%",
                color: "var(--text-muted, #737373)",
                background: "transparent",
                border: "none",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                flexShrink: 0,
                transition: "color 0.15s, background 0.15s",
              }}
              className="hover:text-zinc-200 hover:bg-zinc-700/50"
              aria-label="Attach files"
            >
              <Paperclip size={17} />
            </Button>
          </div>

          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <textarea
              ref={textareaRef}
              value={text}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={isStreaming ? "AI is responding..." : "Message Hybrid RAG..."}
              rows={1}
              disabled={!isOnline || isStreaming}
              style={{
                flex: 1,
                maxHeight: "200px",
                minHeight: "52px",
                background: "transparent",
                border: "none",
                color: "var(--text-primary, #F5F5F5)",
                fontSize: "15px",
                padding: "16px 8px 16px 8px",
                resize: "none",
                outline: "none",
                boxShadow: "none",
                lineHeight: 1.55,
                fontFamily: "inherit",
                width: "100%",
              }}
              className="placeholder:text-zinc-500 disabled:opacity-50 scrollbar-none"
              aria-label="Message prompt input"
            />

            {showCommands && (
              <Command className="absolute bottom-full left-0 right-0 mb-2 bg-[var(--bg-secondary,#171717)] border border-[var(--border-color)] rounded-2xl shadow-xl overflow-hidden animate-slide-up z-10 text-zinc-300">
                <CommandInput
                  value={commandSearch}
                  onValueChange={setCommandSearch}
                  placeholder="Search commands..."
                  className="h-10 px-4 bg-transparent border-0 text-zinc-100 text-sm placeholder:text-zinc-500 focus-visible:ring-0 focus:outline-none"
                  autoFocus
                />
                <CommandEmpty className="py-6 text-center text-zinc-500 text-sm">No commands found.</CommandEmpty>
                <CommandGroup>
                  {filteredCommands.map((cmd) => (
                    <CommandItem
                      key={cmd.id}
                      onSelect={() => handleCommandSelect(cmd)}
                      className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-zinc-900/50 cursor-pointer"
                    >
                      <span className="text-base">{cmd.icon}</span>
                      <div style={{ flex: 1, textAlign: "left" }}>
                        <div style={{ fontWeight: 500, color: "#f5f5f5", fontSize: "14px" }}>{cmd.label}</div>
                        <div style={{ fontSize: "12px", color: "#737373" }}>{cmd.description}</div>
                      </div>
                      <kbd style={{ padding: "2px 6px", fontSize: "11px", fontFamily: "monospace", background: "#27272a", color: "#a3a3a3", borderRadius: "4px" }}>{cmd.shortcut}</kbd>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </Command>
            )}
          </div>

          {/* Right Action buttons: Voice & Send */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px", paddingRight: "12px", paddingLeft: "4px", paddingBottom: "10px", paddingTop: "10px" }}>
            {/* Voice Input */}
            {onVoiceInput && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => { onVoiceInput(); setIsRecording(!isRecording); }}
                disabled={isStreaming}
                style={{
                  width: "38px",
                  height: "38px",
                  borderRadius: "50%",
                  background: isRecording ? "#ef4444" : "transparent",
                  border: "none",
                  color: isRecording ? "white" : "var(--text-muted, #737373)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  flexShrink: 0,
                  transition: "all 0.15s",
                }}
                className={cn(isRecording ? "animate-pulse" : "hover:text-zinc-200 hover:bg-zinc-700/50")}
                aria-label={isRecording ? "Stop recording" : "Record voice"}
                aria-pressed={isRecording}
              >
                <Mic size={17} />
              </Button>
            )}

            {/* Send / Stop Button */}
            {isStreaming ? (
              <Button
                type="button"
                onClick={onStop}
                size="icon"
                style={{
                  width: "36px",
                  height: "36px",
                  background: "#f5f5f5",
                  border: "none",
                  borderRadius: "50%",
                  color: "#0a0a0a",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  flexShrink: 0,
                  transition: "all 0.15s",
                }}
                className="hover:bg-zinc-200 active:scale-95"
                aria-label="Stop generation"
              >
                <Square size={9} fill="currentColor" />
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={!hasContent || !isOnline}
                size="icon"
                style={{
                  width: "36px",
                  height: "36px",
                  background: hasContent && isOnline ? "#f5f5f5" : "rgba(255,255,255,0.08)",
                  border: "none",
                  borderRadius: "50%",
                  color: hasContent && isOnline ? "#0a0a0a" : "var(--text-muted, #737373)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: hasContent && isOnline ? "pointer" : "not-allowed",
                  flexShrink: 0,
                  transition: "all 0.15s",
                }}
                className="active:scale-95"
                aria-label="Send query"
              >
                <ArrowUp size={16} strokeWidth={2.5} />
              </Button>
            )}
          </div>
        </div>

        {/* Character count */}
        {(isNearingLimit || attachments.length > 0) && (
          <div
            style={{
              fontSize: "11px",
              fontFamily: "monospace",
              textAlign: "right",
              alignSelf: "flex-end",
              padding: "0 4px",
              color: isOverLimit ? "#f87171" : "var(--text-muted, #737373)",
              fontWeight: isOverLimit ? 700 : 400,
              transition: "color 0.2s",
            }}
          >
            {charCount} / 4000 {attachments.length > 0 && `· ${attachments.length} files`}
          </div>
        )}
      </div>
    </form>
  );
};