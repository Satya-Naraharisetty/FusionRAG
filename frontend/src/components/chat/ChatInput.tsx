import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { Square, AlertCircle, Paperclip, Mic, X, ArrowUp, History, Trash2, FileText } from "lucide-react";
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
import { useDocuments } from "../../hooks/useDocuments";
import {
  useUploadQueue,
  type QueueFile,
} from "../../context/UploadQueueContext";
import { getDocumentProcessingStep } from "../../lib/uploadStages";
import { UPLOAD_LIMITS } from "../../lib/constants";
import { t } from "../../lib/messages";
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

// Static per-command data — ids, icons, and shortcuts aren't translatable.
// Labels and descriptions resolve through messages.ts on every render (see
// the slashCommands map in the component) so a locale change is reflected
// immediately.
const SLASH_COMMAND_DEFS = [
  { id: "documents", labelKey: "commands.documents.label", descriptionKey: "commands.documents.description", icon: "📎", shortcut: "@documents" },
  { id: "search", labelKey: "commands.search.label", descriptionKey: "commands.search.description", icon: "🔍", shortcut: "/search" },
  { id: "summarize", labelKey: "commands.summarize.label", descriptionKey: "commands.summarize.description", icon: "📄", shortcut: "/summarize" },
  { id: "explain", labelKey: "commands.explain.label", descriptionKey: "commands.explain.description", icon: "💡", shortcut: "/explain" },
  { id: "compare", labelKey: "commands.compare.label", descriptionKey: "commands.compare.description", icon: "⚖️", shortcut: "/compare" },
  { id: "code", labelKey: "commands.code.label", descriptionKey: "commands.code.description", icon: "💻", shortcut: "/code" },
  { id: "settings", labelKey: "commands.settings.label", descriptionKey: "commands.settings.description", icon: "⚙️", shortcut: "/settings" },
] as const;

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
  const [isRecording, setIsRecording] = useState(false);
  const [isDraggingOver, setIsDraggingOver] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<unknown>(null);

  // The queue (app-level) owns the uploads — progress, the processing→done
  // flip, and persistence across navigation — so this tray is a scoped view
  // of its rows for the current conversation.
  const {
    queue,
    embeddingStatus,
    addFiles,
    cancelUpload,
    removeItems,
  } = useUploadQueue();
  // Shared cache (deduped with the Documents page/sidebar): refetches every 5s
  // while documents are pending/processing, plus the embedding-status poll.
  const { data: documents = [] } = useDocuments();

  // Rows this composer created (chat rows), scoped to its conversation.
  const chatRows = useMemo(
    () =>
      queue.filter(
        (q) =>
          q.source === "chat" &&
          (q.conversationId ?? null) === (conversationId ?? null)
      ),
    [queue, conversationId]
  );

  const chatExtensions = useMemo(
    () =>
      Object.values(UPLOAD_LIMITS.CHAT_ACCEPTED_TYPES)
        .flat()
        .map((ext) => ext.replace(/^\./, "")),
    []
  );

  const { validateFiles } = useFileValidation({
    maxSize: UPLOAD_LIMITS.CHAT_MAX_FILE_SIZE,
    acceptedTypes: UPLOAD_LIMITS.CHAT_ACCEPTED_TYPES,
    existingFiles: chatRows
      .filter((row): row is QueueFile & { file: File } => Boolean(row.file))
      .map((row) => ({ file: row.file })),
    checkDuplicates: true,
  });

  const { recents, addRecent, clearRecents } = useRecentAttachments();

  const handleAddFiles = useCallback(
    (files: File[]) => {
      const { valid } = validateFiles(files);
      if (valid.length === 0) return;
      const room = UPLOAD_LIMITS.CHAT_MAX_ATTACHMENTS - chatRows.length;
      if (room <= 0) {
        toast.error(
          t("chat.uploadLimit", { max: UPLOAD_LIMITS.CHAT_MAX_ATTACHMENTS })
        );
        return;
      }
      if (valid.length > room) {
        toast.error(
          t(room === 1 ? "chat.uploadRoomOne" : "chat.uploadRoomOther", {
            room,
            max: UPLOAD_LIMITS.CHAT_MAX_ATTACHMENTS,
          })
        );
      }
      addFiles(valid.slice(0, room), {
        source: "chat",
        conversationId: conversationId ?? undefined,
        maxSize: UPLOAD_LIMITS.CHAT_MAX_FILE_SIZE,
        acceptedExtensions: chatExtensions,
        // A brand-new chat has no conversation yet (the backend creates it on
        // the first message), so its attachments can't be scoped — they stay
        // queued and are handed to the conversation once it exists (see
        // ChatWindow's flush). Existing conversations upload immediately.
        autoUpload: Boolean(conversationId),
        silent: true,
        getPreview: (file) =>
          file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
        onUploaded: addRecent,
      });
    },
    [validateFiles, chatRows.length, conversationId, chatExtensions, addFiles, addRecent]
  );

  useEffect(() => {
    if (droppedFiles && droppedFiles.length > 0) {
      handleAddFiles(droppedFiles);
    }
  }, [droppedFiles, handleAddFiles]);

  // Shared documents cache, used to derive the live pipeline step for rows
  // currently ingesting server-side. (The processing→done flip itself lives
  // in the queue provider.)
  const docById = useMemo(
    () => new Map(documents.map((d) => [d.id, d])),
    [documents]
  );

  const handleFileSelect = (files: FileList | null) => {
    if (!files) return;
    handleAddFiles(Array.from(files));
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // Cancelling removes the row from the queue (aborting an in-flight upload
  // and revoking its preview), matching the old tray's remove behavior.
  const removeAttachment = (id: string) => cancelUpload(id);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = text.trim();
    if ((!trimmed && chatRows.length === 0) || isStreaming || !isOnline) return;

    const rawFiles = chatRows
      .map((a) => a.file)
      .filter((f): f is File => Boolean(f));
    onSend(trimmed, rawFiles.length > 0 ? rawFiles : undefined);

    setText("");
    // The uploads keep running server-side; the rows are dismissed from the
    // tray now that they've been attached to the message. In a brand-new chat
    // the conversation doesn't exist yet — those rows stay queued so they can
    // be handed to the conversation once it's created (not lost here).
    if (conversationId) {
      removeItems(chatRows.map((r) => r.id));
    }
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
  }, [text, adjustHeight]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);
    setDraft(val);
    adjustHeight();
  };

  const toggleSpeechRecognition = useCallback(() => {
    if (typeof window === "undefined") return;

    interface IWindowWithSpeech extends Window {
      SpeechRecognition?: new () => ISpeechRecognition;
      webkitSpeechRecognition?: new () => ISpeechRecognition;
    }

    interface ISpeechRecognitionEvent {
      results?: Array<Array<{ transcript?: string }>>;
    }

    interface ISpeechRecognition {
      continuous: boolean;
      interimResults: boolean;
      lang: string;
      onstart: () => void;
      onresult: (event: ISpeechRecognitionEvent) => void;
      onerror: () => void;
      onend: () => void;
      start: () => void;
      stop: () => void;
    }

    const win = window as unknown as IWindowWithSpeech;
    const SpeechRecognitionClass = win.SpeechRecognition || win.webkitSpeechRecognition;

    if (!SpeechRecognitionClass) {
      toast("Voice dictation is supported in Chrome, Edge, and Safari.", { icon: "🎙️" });
      return;
    }

    if (isRecording) {
      if (recognitionRef.current && typeof (recognitionRef.current as ISpeechRecognition).stop === "function") {
        (recognitionRef.current as ISpeechRecognition).stop();
      }
      setIsRecording(false);
      return;
    }

    try {
      const recognition = new SpeechRecognitionClass();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        setIsRecording(true);
      };

      recognition.onresult = (event: ISpeechRecognitionEvent) => {
        const transcript = event.results?.[0]?.[0]?.transcript;
        if (transcript) {
          setText((prev) => (prev ? `${prev} ${transcript.trim()}` : transcript.trim()));
          adjustHeight();
        }
      };

      recognition.onerror = () => {
        setIsRecording(false);
      };

      recognition.onend = () => {
        setIsRecording(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch {
      setIsRecording(false);
    }
  }, [isRecording, adjustHeight]);

  // Global keyboard shortcuts (Esc to stop streaming, Ctrl+Shift+O for new chat)
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isStreaming) {
        e.preventDefault();
        onStop();
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [isStreaming, onStop]);

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
      if (isStreaming) {
        onStop();
      }
    }
  };

  // Resolve translatable command copy on every render so the next render
  // after a locale change (Settings → Appearance → Language) picks up the new
  // locale. t() itself is not reactive — the module has no subscription — so
  // labels refresh on re-render, not instantly.
  const slashCommands = SLASH_COMMAND_DEFS.map((def) => ({
    id: def.id,
    label: t(def.labelKey),
    description: t(def.descriptionKey),
    icon: def.icon,
    shortcut: def.shortcut,
  }));

  const filteredCommands = commandSearch
    ? slashCommands.filter(
        (c) =>
          c.label.toLowerCase().includes(commandSearch.toLowerCase()) ||
          c.description.toLowerCase().includes(commandSearch.toLowerCase())
      )
    : slashCommands;

  const handleCommandSelect = (cmd: (typeof slashCommands)[number]) => {
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

  // Active when the user typed the @documents priority mention. Matches the
  // backend's (?<!\w)@documents\b so e.g. "email@documents.com" doesn't count.
  const isDocMode = useMemo(() => /(?<!\w)@documents\b/i.test(text), [text]);

  // Pure derivation from the draft — no effect-driven state copy (the old
  // setCharCount-in-effect scheduled an update during every passive flush,
  // which React's nested-passive-update detector counted across keystrokes
  // and eventually flagged as "Maximum update depth exceeded").
  const charCount = text.length;
  const isNearingLimit = charCount > 3000;
  const isOverLimit = charCount > 4000;
  const hasContent = text.trim().length > 0 || chatRows.length > 0;

  return (
    <form
      onSubmit={handleSubmit}
      className="relative w-full max-w-[860px] select-none px-4 sm:px-6"
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={Object.values(UPLOAD_LIMITS.CHAT_ACCEPTED_TYPES)
          .flat()
          .map((ext) => (ext.startsWith(".") ? ext : `.${ext}`))
          .join(",")}
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
            <span>{t("chat.offlineWarning")}</span>
          </div>
        )}

        {/* Document-priority indicator (active when @documents is in the message) */}
        {isDocMode && (
          <div className="flex items-center gap-1.5 self-start rounded-[10px] border border-(--accent-primary)/25 bg-(--accent-primary)/8 px-3 py-1.5 text-xs font-medium text-(--accent-primary)">
            <FileText size={12} />
            <span>{t("chat.documentMode")}</span>
          </div>
        )}

        {/* Attachments Preview Tray — rows live in the app-level queue, so
            uploads keep running (and stay visible) after navigating away. */}
        {chatRows.length > 0 && (
          <div className="space-y-1.5">
          <div className="flex flex-wrap gap-2 px-1">
            {chatRows.map((att) => {
              // While the document ingests server-side, derive the live
              // pipeline step (Extracting/Chunking/Indexing) from shared state.
              const docId = att.documentId;
              const doc = docId ? docById.get(docId) : undefined;
              const stage =
                att.status === "processing" && doc && docId
                  ? getDocumentProcessingStep(doc, embeddingStatus[docId])
                  : null;
              return (
                <div
                  key={att.id}
                  className="flex items-center gap-2 rounded-xl border border-(--border-default) bg-(--bg-tertiary) p-1.5 pr-2.5 transition-colors"
                >
                  {att.preview ? (
                    <img
                      src={att.preview}
                      alt={att.fileName}
                      className="h-8 w-8 shrink-0 rounded-md border border-(--border-subtle) object-cover"
                    />
                  ) : (
                    <FileTypeBadge filename={att.fileName} variant="card" className="h-8 w-8 text-[8px]" />
                  )}

                  <div className="min-w-0 max-w-32.5 space-y-0.5">
                    <p className="truncate text-xs font-medium leading-none text-(--text-primary)">
                      {att.fileName}
                    </p>
                    {att.file && (
                      <p className="font-mono text-[10px] leading-none text-(--text-muted)">
                        {(att.file.size / 1024).toFixed(0)} KB
                      </p>
                    )}
                  </div>

                  <UploadProgress
                    progress={stage ? stage.progress : att.progress}
                    status={stage ? "processing" : att.status}
                    size="sm"
                    showLabel={
                      att.status === "uploading" || att.status === "processing"
                    }
                    footer={
                      stage
                        ? stage.detail
                        : att.status === "error" && !att.detail
                        ? t("chat.uploadFailed")
                        : att.detail
                    }
                  />

                  <button
                    type="button"
                    onClick={() => removeAttachment(att.id)}
                    className="ml-0.5 cursor-pointer rounded-sm p-1 text-(--text-muted) transition-colors hover:text-(--accent-error)"
                    aria-label={t("chatFiles.removeAria", {
                      filename: att.fileName,
                    })}
                  >
                    <X size={12} />
                  </button>
                </div>
              );
            })}
          </div>
          {/* Same lifecycle hint as the persisted chips strip: these files are
              scoped to this chat, never the global library, and die with the
              conversation. */}
          <div className="flex items-center gap-1.5 px-2 pb-0.5 text-[11px] font-medium leading-snug text-[var(--text-muted)]">
            <Paperclip size={11} className="flex-shrink-0 opacity-60" />
            <span>{t("chatFiles.caption")}</span>
          </div>
          </div>
        )}

        {/* Brand-new chat with nothing attached yet — the same lifecycle note.
            (For existing conversations the chips strip owns this hint.) */}
        {conversationId === null && chatRows.length === 0 && (
          <div className="flex items-center gap-1.5 px-2 pb-0.5 text-[11px] font-medium leading-snug text-[var(--text-muted)]">
            <Paperclip size={11} className="flex-shrink-0 opacity-60" />
            <span>{t("chatFiles.caption")}</span>
          </div>
        )}

        {/* Input Wrapper — Premium composer with Drag & Drop */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            "relative flex items-end rounded-[20px] sm:rounded-[24px] border bg-[var(--bg-secondary)] transition-all duration-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_4px_24px_rgba(0,0,0,0.4)] focus-within:bg-[var(--bg-elevated)] focus-within:border-[var(--accent-primary)]/40 focus-within:shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_0_24px_rgba(0,210,253,0.12),0_4px_24px_rgba(0,0,0,0.5)]",
            isDraggingOver
              ? "border-dashed border-[var(--accent-primary)]/70 bg-[var(--accent-primary)]/8"
              : "border-[var(--border-default)] hover:border-[var(--border-hover)]",
            isRecording && "border-[var(--accent-error)]/45 bg-red-950/10"
          )}
        >
          {/* Paperclip button with Recent Attachments dropdown */}
          <div className="flex items-center justify-center pl-3.5 pr-1.5 pb-2.5 pt-2.5">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={
                    isStreaming ||
                    chatRows.length >= UPLOAD_LIMITS.CHAT_MAX_ATTACHMENTS
                  }
                  className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                  aria-label="Attach files options"
                >
                  <Paperclip size={18} />
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
                      <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                        <History size={10} /> Recent Files
                      </span>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); clearRecents(); }}
                        className="cursor-pointer p-0.5 text-[10px] text-[var(--text-muted)] hover:text-[var(--accent-error)]"
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
                        <span className="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">
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
                  ? t("chat.placeholderDrop")
                  : isStreaming
                  ? t("chat.placeholderStreaming")
                  : t("chat.placeholderDefault")
              }
              rows={1}
              disabled={!isOnline || isStreaming}
              className="min-h-[58px] max-h-52 w-full flex-1 resize-none border-0 bg-transparent px-2 py-3.5 sm:py-4 text-[15px] sm:text-[16px] leading-relaxed text-[var(--text-primary)] shadow-none outline-none placeholder:text-[var(--text-muted)] disabled:opacity-50 scrollbar-none"
              aria-label="Message prompt input"
            />

            {showCommands && (
              <Command className="absolute bottom-full left-0 right-0 z-10 mb-2 overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--text-primary)] shadow-md animate-in fade-in slide-in-from-bottom-2 duration-150">
                <CommandInput
                  value={commandSearch}
                  onValueChange={setCommandSearch}
                  placeholder={t("chat.commandSearchPlaceholder")}
                  className="h-10 bg-transparent border-0 text-sm focus-visible:ring-0 focus:outline-none"
                  autoFocus
                />
                <CommandEmpty className="py-4 text-center text-xs text-[var(--text-muted)]">
                  {t("chat.commandEmpty")}
                </CommandEmpty>
                <CommandGroup>
                  {filteredCommands.map((cmd) => (
                    <CommandItem
                      key={cmd.id}
                      onSelect={() => handleCommandSelect(cmd)}
                      className="flex items-center gap-3 px-3 py-2 cursor-pointer"
                    >
                      <span className="shrink-0 text-base">{cmd.icon}</span>
                      <div className="flex-1 text-left min-w-0">
                        <div className="truncate text-sm font-medium text-[var(--text-primary)]">{cmd.label}</div>
                        <div className="truncate text-xs text-[var(--text-muted)]">{cmd.description}</div>
                      </div>
                      <kbd className="shrink-0 rounded-sm border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                        {cmd.shortcut}
                      </kbd>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </Command>
            )}
          </div>

          {/* Right Action buttons: Voice & Send */}
          <div className="flex items-center gap-1.5 px-3 pl-1 pb-2.5 pt-2.5">
            {/* Voice Input */}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => {
                if (onVoiceInput) onVoiceInput();
                toggleSpeechRecognition();
              }}
              disabled={isStreaming}
              className={cn(
                "h-10 w-10 shrink-0 rounded-full border transition-colors cursor-pointer",
                isRecording
                  ? "border-[var(--accent-error)]/20 bg-[var(--accent-error)]/12 text-[var(--accent-error)] animate-pulse"
                  : "border-transparent text-[var(--text-muted)] hover:border-[var(--border-subtle)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
              )}
              aria-label={isRecording ? "Stop recording" : "Record voice"}
              data-pressed={isRecording}
            >
              <Mic size={18} />
            </Button>

            {/* Send / Stop Button */}
            {isStreaming ? (
              <Button
                type="button"
                onClick={onStop}
                size="icon"
                className="h-10 w-10 shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--text-primary)] transition-all hover:bg-[var(--bg-tertiary)] active:scale-95"
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
                  "h-10 w-10 shrink-0 rounded-full border transition-all duration-150 active:scale-95",
                  hasContent && isOnline
                    ? "border-transparent bg-[image:var(--gradient-main)] text-slate-950 font-semibold shadow-[0_0_16px_rgba(0,210,253,0.3)] hover:brightness-110"
                    : "border-[var(--border-subtle)] bg-[var(--bg-tertiary)] text-[var(--text-muted)] cursor-not-allowed opacity-60"
                )}
                aria-label="Send query"
              >
                <ArrowUp size={18} strokeWidth={2.5} />
              </Button>
            )}
          </div>
        </div>

        {/* Character count */}
        {(isNearingLimit || chatRows.length > 0) && (
          <div className={cn(
            "self-end px-1 text-right font-mono text-[11px] transition-colors",
            isOverLimit ? "font-semibold text-(--accent-error)" : "text-(--text-muted)"
          )}>
            {charCount} / 4000 {chatRows.length > 0 && `· ${chatRows.length} files`}
          </div>
        )}
      </div>
    </form>
  );
};

export default ChatInput;