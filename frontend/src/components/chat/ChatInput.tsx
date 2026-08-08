import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { Square, AlertCircle, Paperclip, Mic, X, ArrowUp, History, Trash2 } from "lucide-react";
import { Button } from "../ui/Button";
import { useDraft } from "../../hooks/useDrafts";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem } from "../ui/command";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "../ui/Dropdown";
import { FileTypeBadge } from "../ui/FileTypeBadge";
import { UploadProgress } from "../ui/UploadProgress";
import { useFileValidation } from "../../hooks/useFileValidation";
import { useRecentAttachments } from "../../hooks/useRecentAttachments";
import { useUploadDocument } from "../../hooks/useDocuments";
import { ChatAttachment } from "../../types";
import { UPLOAD_LIMITS } from "../../lib/constants";
import toast from "react-hot-toast";
import { cn } from "../../lib/utils";

interface ChatInputProps {
  conversationId: string | null;
  onSend: (text: string, attachments?: File[]) => void;
  onStop: () => void;
  isStreaming: boolean;
  onVoiceInput?: () => void;
  droppedFiles?: File[];
}

const SLASH_COMMANDS = [
  { id: "search", label: "Search documents", description: "Query your knowledge base", icon: "🔍", shortcut: "/search" },
  { id: "summarize", label: "Summarize", description: "Summarize selected documents", icon: "📄", shortcut: "/summarize" },
  { id: "explain", label: "Explain concept", description: "Get detailed explanation", icon: "💡", shortcut: "/explain" },
  { id: "compare", label: "Compare", description: "Compare two documents", icon: "⚖️", shortcut: "/compare" },
  { id: "code", label: "Code helper", description: "Generate or explain code", icon: "💻", shortcut: "/code" },
  { id: "settings", label: "Settings", description: "Open settings panel", icon: "⚙️", shortcut: "/settings" },
];

export const ChatInput: React.FC<ChatInputProps> = ({
  conversationId,
  onSend,
  onStop,
  isStreaming,
  onVoiceInput,
  droppedFiles,
}) => {
  const { draft, setDraft, clearDraft } = useDraft(conversationId);
  const { isOnline } = useOnlineStatus();
  const [text, setText] = useState(draft);
  const [showCommands, setShowCommands] = useState(false);
  const [commandSearch, setCommandSearch] = useState("");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [charCount, setCharCount] = useState(0);
  const [isDraggingOver, setIsDraggingOver] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { validateFiles } = useFileValidation({
    maxSize: UPLOAD_LIMITS.CHAT_MAX_FILE_SIZE,
    acceptedTypes: UPLOAD_LIMITS.CHAT_ACCEPTED_TYPES,
    existingFiles: attachments,
    checkDuplicates: true,
  });

  const { recents, addRecent, clearRecents } = useRecentAttachments();
  const uploadMutation = useUploadDocument();

  const handleAddFiles = useCallback(
    (files: File[]) => {
      const { valid } = validateFiles(files);
      if (valid.length === 0) return;

      const newAttachments: ChatAttachment[] = valid.map((file) => ({
        id: `att-${Math.random().toString(36).substring(2, 9)}`,
        file,
        preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
        status: "uploading",
        progress: 0,
      }));

      setAttachments((prev) => [...prev, ...newAttachments].slice(0, 5));

      newAttachments.forEach(async (att) => {
        try {
          const doc = await uploadMutation.mutateAsync({
            file: att.file,
            onProgress: (evt: unknown) => {
              const pe = evt as { loaded: number; total?: number };
              const progress = pe.total ? Math.round((pe.loaded * 100) / pe.total) : 0;
              setAttachments((prev) =>
                prev.map((a) => (a.id === att.id ? { ...a, progress } : a))
              );
            },
          });

          setAttachments((prev) =>
            prev.map((a) =>
              a.id === att.id
                ? { ...a, status: "completed", progress: 100, documentId: doc.id }
                : a
            )
          );
          addRecent(att.file);
        } catch (err: unknown) {
          setAttachments((prev) =>
            prev.map((a) => (a.id === att.id ? { ...a, status: "error", error: "Upload failed" } : a))
          );
          toast.error(`Failed to upload "${att.file.name}"`);
        }
      });
    },
    [validateFiles, uploadMutation, addRecent]
  );

  useEffect(() => {
    if (droppedFiles && droppedFiles.length > 0) {
      handleAddFiles(droppedFiles);
    }
  }, [droppedFiles, handleAddFiles]);

  const handleFileSelect = (files: FileList | null) => {
    if (!files) return;
    handleAddFiles(Array.from(files));
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const item = prev.find((a) => a.id === id);
      if (item?.preview) {
        URL.revokeObjectURL(item.preview);
      }
      return prev.filter((a) => a.id !== id);
    });
  };

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || isStreaming || !isOnline) return;

    const rawFiles = attachments.map((a) => a.file);
    onSend(trimmed, rawFiles.length > 0 ? rawFiles : undefined);

    setText("");
    setAttachments([]);
    clearDraft();
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

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

  const handleCommandSelect = (cmd: typeof SLASH_COMMANDS[0]) => {
    setText(cmd.shortcut + " ");
    setShowCommands(false);
    textareaRef.current?.focus();
  };

  // Drag and drop events for input wrapper
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDraggingOver) setIsDraggingOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleAddFiles(Array.from(e.dataTransfer.files));
    }
  };

  const filteredCommands = useMemo(() => {
    if (!commandSearch) return SLASH_COMMANDS;
    return SLASH_COMMANDS.filter(
      (c) =>
        c.label.toLowerCase().includes(commandSearch.toLowerCase()) ||
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
        accept={Object.values(UPLOAD_LIMITS.CHAT_ACCEPTED_TYPES).flat().map((ext) => `.${ext}`).join(",")}
        onChange={(e) => handleFileSelect(e.target.files)}
        className="hidden"
        id="chat-file-input"
      />

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {/* Offline Warning Alert */}
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
          <div className="flex flex-wrap gap-2 px-1">
            {attachments.map((att) => (
              <div
                key={att.id}
                className="flex items-center gap-2 p-1.5 pr-2.5 bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-[var(--radius-xl)] transition-colors"
              >
                {att.preview ? (
                  <img
                    src={att.preview}
                    alt={att.file.name}
                    className="w-8 h-8 rounded-[var(--radius-md)] object-cover flex-shrink-0 border border-[var(--border-subtle)]"
                  />
                ) : (
                  <FileTypeBadge filename={att.file.name} variant="card" className="w-8 h-8 text-[8px]" />
                )}

                <div className="min-w-0 max-w-[130px] space-y-0.5">
                  <p className="text-xs font-medium text-[var(--text-primary)] truncate leading-none">
                    {att.file.name}
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)] font-mono leading-none">
                    {(att.file.size / 1024).toFixed(0)} KB
                  </p>
                </div>

                <UploadProgress progress={att.progress} status={att.status} size="sm" showLabel={att.status === "uploading"} />

                <button
                  type="button"
                  onClick={() => removeAttachment(att.id)}
                  className="p-1 text-[var(--text-muted)] hover:text-[var(--accent-error)] rounded-[var(--radius-sm)] transition-colors cursor-pointer ml-0.5"
                  aria-label={`Remove ${att.file.name}`}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input Wrapper — Premium composer with Drag & Drop */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          style={{
            position: "relative",
            display: "flex",
            alignItems: "flex-end",
            background: "var(--bg-input, #2A2A2A)",
            border: isDraggingOver
              ? "2px dashed #8b5cf6"
              : "1px solid rgba(255,255,255,0.10)",
            borderRadius: "20px",
            boxShadow: isDraggingOver
              ? "0 0 25px rgba(139, 92, 246, 0.35)"
              : "0 4px 20px rgba(0,0,0,0.25)",
            transition: "all 0.2s ease",
          }}
          className={cn(
            "focus-within:border-white/[0.18] focus-within:shadow-[0_8px_32px_rgba(0,0,0,0.35)]",
            isRecording && "border-red-500/40",
            isDraggingOver && "bg-violet-950/20"
          )}
        >
          {/* Paperclip button with Recent Attachments dropdown */}
          <div className="flex items-center justify-center pl-3 pr-1 pb-2.5 pt-2.5">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={isStreaming || attachments.length >= 5}
                  className="h-9 w-9 rounded-full text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] cursor-pointer flex items-center justify-center transition-colors"
                  aria-label="Attach files options"
                >
                  <Paperclip size={17} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" side="top" className="w-56">
                <DropdownMenuItem
                  onClick={() => fileInputRef.current?.click()}
                  className="gap-2 cursor-pointer"
                >
                  <Paperclip size={14} className="text-[var(--accent-primary)]" />
                  <span>Upload from computer…</span>
                </DropdownMenuItem>

                {recents.length > 0 && (
                  <>
                    <DropdownMenuSeparator />
                    <div className="flex items-center justify-between px-2 py-1">
                      <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1">
                        <History size={10} /> Recent Files
                      </span>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); clearRecents(); }}
                        className="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent-error)] p-0.5 cursor-pointer"
                        title="Clear recent list"
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>

                    {recents.slice(0, 5).map((rec, idx) => (
                      <DropdownMenuItem
                        key={rec.name + idx}
                        onClick={() => { toast.success(`Selected: "${rec.name}"`); }}
                        className="flex items-center justify-between cursor-pointer py-1.5"
                      >
                        <span className="truncate max-w-[130px] font-medium">{rec.name}</span>
                        <span className="text-[10px] text-[var(--text-muted)] font-mono flex-shrink-0">
                          {(rec.size / 1024).toFixed(0)} KB
                        </span>
                      </DropdownMenuItem>
                    ))}
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <textarea
              ref={textareaRef}
              value={text}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={
                isDraggingOver
                  ? "Drop files here to attach..."
                  : isStreaming
                  ? "AI is responding..."
                  : "Message Hybrid RAG..."
              }
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
              className="placeholder:text-[var(--text-muted)] disabled:opacity-50 scrollbar-none"
              aria-label="Message prompt input"
            />

            {showCommands && (
              <Command className="absolute bottom-full left-0 right-0 mb-2 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-[var(--radius-2xl)] shadow-md overflow-hidden z-10 text-[var(--text-primary)] animate-in fade-in slide-in-from-bottom-2 duration-150">
                <CommandInput
                  value={commandSearch}
                  onValueChange={setCommandSearch}
                  placeholder="Search commands…"
                  className="h-10 bg-transparent border-0 text-sm focus-visible:ring-0 focus:outline-none"
                  autoFocus
                />
                <CommandEmpty className="py-4 text-center text-[var(--text-muted)] text-xs">No commands found.</CommandEmpty>
                <CommandGroup>
                  {filteredCommands.map((cmd) => (
                    <CommandItem
                      key={cmd.id}
                      onSelect={() => handleCommandSelect(cmd)}
                      className="flex items-center gap-3 px-3 py-2 cursor-pointer"
                    >
                      <span className="text-base flex-shrink-0">{cmd.icon}</span>
                      <div className="flex-1 text-left min-w-0">
                        <div className="text-sm font-medium text-[var(--text-primary)] truncate">{cmd.label}</div>
                        <div className="text-xs text-[var(--text-muted)] truncate">{cmd.description}</div>
                      </div>
                      <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-[var(--bg-tertiary)] text-[var(--text-muted)] rounded-[var(--radius-sm)] border border-[var(--border-subtle)] flex-shrink-0">
                        {cmd.shortcut}
                      </kbd>
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
                className={cn(isRecording ? "animate-pulse" : "hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]")}
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
                className="hover:bg-[var(--bg-tertiary)] active:scale-95"
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

export default ChatInput;