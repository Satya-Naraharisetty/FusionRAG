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
      className="relative w-full max-w-195 select-none px-5"
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={Object.values(UPLOAD_LIMITS.CHAT_ACCEPTED_TYPES).flat().map((ext) => `.${ext}`).join(",")}
        onChange={(e) => handleFileSelect(e.target.files)}
        className="hidden"
        id="chat-file-input"
        aria-label="Attach files"
      />

      <div className="flex flex-col gap-2">
        {/* Offline Warning Alert */}
        {!isOnline && (
          <div className="flex items-center gap-1.5 rounded-[10px] border border-[rgba(248,113,113,0.15)] bg-[rgba(248,113,113,0.08)] px-3 py-2 text-xs font-semibold text-red-400">
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
                className="flex items-center gap-2 rounded-xl border border-(--border-default) bg-(--bg-tertiary) p-1.5 pr-2.5 transition-colors"
              >
                {att.preview ? (
                  <img
                    src={att.preview}
                    alt={att.file.name}
                    className="h-8 w-8 shrink-0 rounded-md border border-(--border-subtle) object-cover"
                  />
                ) : (
                  <FileTypeBadge filename={att.file.name} variant="card" className="h-8 w-8 text-[8px]" />
                )}

                <div className="min-w-0 max-w-32.5 space-y-0.5">
                  <p className="truncate text-xs font-medium leading-none text-(--text-primary)">
                    {att.file.name}
                  </p>
                  <p className="font-mono text-[10px] leading-none text-(--text-muted)">
                    {(att.file.size / 1024).toFixed(0)} KB
                  </p>
                </div>

                <UploadProgress progress={att.progress} status={att.status} size="sm" showLabel={att.status === "uploading"} />

                <button
                  type="button"
                  onClick={() => removeAttachment(att.id)}
                  className="ml-0.5 cursor-pointer rounded-sm p-1 text-(--text-muted) transition-colors hover:text-(--accent-error)"
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
          className={cn(
            "relative flex items-end rounded-[20px] border bg-(--bg-secondary) transition-all duration-200 focus-within:border-(--border-hover) focus-within:shadow-[0_8px_32px_rgba(0,0,0,0.35)]",
            isDraggingOver
              ? "border-dashed border-(--accent-primary)/70 bg-(--accent-primary)/8 shadow-[0_0_25px_rgba(110,168,255,0.18)]"
              : "border-(--border-default) shadow-[0_4px_20px_rgba(0,0,0,0.22)]",
            isRecording && "border-(--accent-error)/45"
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
                  className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-(--text-muted) transition-colors hover:bg-(--bg-tertiary) hover:text-(--text-primary)"
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
                  <Paperclip size={14} className="text-(--accent-primary)" />
                  <span>Upload from computer…</span>
                </DropdownMenuItem>

                {recents.length > 0 && (
                  <>
                    <DropdownMenuSeparator />
                    <div className="flex items-center justify-between px-2 py-1">
                      <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-(--text-muted)">
                        <History size={10} /> Recent Files
                      </span>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); clearRecents(); }}
                        className="cursor-pointer p-0.5 text-[10px] text-(--text-muted) hover:text-(--accent-error)"
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
                        <span className="truncate max-w-32.5 font-medium">{rec.name}</span>
                        <span className="shrink-0 font-mono text-[10px] text-(--text-muted)">
                          {(rec.size / 1024).toFixed(0)} KB
                        </span>
                      </DropdownMenuItem>
                    ))}
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <div className="flex min-w-0 flex-1 flex-col">
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
              className="min-h-13 max-h-50 w-full flex-1 resize-none border-0 bg-transparent px-2 py-4 text-[15px] leading-[1.55] text-(--text-primary) shadow-none outline-none placeholder:text-(--text-muted) disabled:opacity-50 scrollbar-none"
              aria-label="Message prompt input"
            />

            {showCommands && (
              <Command className="absolute bottom-full left-0 right-0 z-10 mb-2 overflow-hidden rounded-2xl border border-(--border-subtle) bg-(--bg-elevated) text-(--text-primary) shadow-md animate-in fade-in slide-in-from-bottom-2 duration-150">
                <CommandInput
                  value={commandSearch}
                  onValueChange={setCommandSearch}
                  placeholder="Search commands…"
                  className="h-10 bg-transparent border-0 text-sm focus-visible:ring-0 focus:outline-none"
                  autoFocus
                />
                <CommandEmpty className="py-4 text-center text-xs text-(--text-muted)">No commands found.</CommandEmpty>
                <CommandGroup>
                  {filteredCommands.map((cmd) => (
                    <CommandItem
                      key={cmd.id}
                      onSelect={() => handleCommandSelect(cmd)}
                      className="flex items-center gap-3 px-3 py-2 cursor-pointer"
                    >
                      <span className="shrink-0 text-base">{cmd.icon}</span>
                      <div className="flex-1 text-left min-w-0">
                        <div className="truncate text-sm font-medium text-(--text-primary)">{cmd.label}</div>
                        <div className="truncate text-xs text-(--text-muted)">{cmd.description}</div>
                      </div>
                      <kbd className="shrink-0 rounded-sm border border-(--border-subtle) bg-(--bg-tertiary) px-1.5 py-0.5 font-mono text-[10px] text-(--text-muted)">
                        {cmd.shortcut}
                      </kbd>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </Command>
            )}
          </div>

          {/* Right Action buttons: Voice & Send */}
          <div className="flex items-center gap-1.5 px-3 pl-1 pt-2.5 pb-2.5">
            {/* Voice Input */}
            {onVoiceInput && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => { onVoiceInput(); setIsRecording(!isRecording); }}
                disabled={isStreaming}
                className={cn(
                  "h-9.5 w-9.5 shrink-0 rounded-full border transition-colors",
                  isRecording
                    ? "border-(--accent-error)/20 bg-(--accent-error)/12 text-(--accent-error) animate-pulse"
                    : "border-transparent text-(--text-muted) hover:border-(--border-subtle) hover:bg-(--bg-tertiary) hover:text-(--text-primary)"
                )}
                aria-label={isRecording ? "Stop recording" : "Record voice"}
                data-pressed={isRecording}
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
                className="h-9 w-9 shrink-0 rounded-full border border-(--border-subtle) bg-(--bg-elevated) text-(--text-primary) transition-all hover:bg-(--bg-tertiary) active:scale-95"
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
                  "h-9 w-9 shrink-0 rounded-full border transition-all active:scale-95",
                  hasContent && isOnline
                    ? "border-(--border-subtle) bg-(--bg-elevated) text-(--text-primary) hover:bg-(--bg-tertiary)"
                    : "border-(--border-subtle) bg-(--bg-tertiary) text-(--text-muted) cursor-not-allowed"
                )}
                aria-label="Send query"
              >
                <ArrowUp size={16} strokeWidth={2.5} />
              </Button>
            )}
          </div>
        </div>

        {/* Character count */}
        {(isNearingLimit || attachments.length > 0) && (
          <div className={cn(
            "self-end px-1 text-right font-mono text-[11px] transition-colors",
            isOverLimit ? "font-semibold text-(--accent-error)" : "text-(--text-muted)"
          )}>
            {charCount} / 4000 {attachments.length > 0 && `· ${attachments.length} files`}
          </div>
        )}
      </div>
    </form>
  );
};

export default ChatInput;