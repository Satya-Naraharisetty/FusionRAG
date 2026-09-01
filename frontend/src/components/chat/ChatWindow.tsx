import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMessages } from "../../hooks/useMessages";
import { useSSEChat } from "../../hooks/useSSEChat";
import { useConversation } from "../../hooks/useConversations";
import { EmptyChat } from "./EmptyChat";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { ChatToolbar } from "./ChatToolbar";
import { ConversationDocumentChips } from "./ConversationDocumentChips";
import { StreamingRecovery } from "./StreamingRecovery";
import { CitationDrawer } from "./CitationDrawer";
import { useUploadQueue } from "../../context/UploadQueueContext";
import { Skeleton } from "../ui/skeleton";
import { AlertCircle, Upload } from "lucide-react";
import { Citation } from "../../types";

interface ChatWindowProps {
  conversationId: string | null;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ conversationId }) => {
  const navigate = useNavigate();
  const { data: messagesData, isLoading, error } = useMessages(conversationId);
  const { data: activeConv } = useConversation(conversationId);
  const [isDraggingWindow, setIsDraggingWindow] = useState(false);
  const [windowDroppedFiles, setWindowDroppedFiles] = useState<File[]>([]);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [isCitationDrawerOpen, setIsCitationDrawerOpen] = useState(false);
  const { uploadQueuedChatRows, discardQueuedNewChatRows } = useUploadQueue();

  const handleConversationCreated = React.useCallback(
    (newId: string) => {
      uploadQueuedChatRows(newId);
      navigate(`/chat/${newId}`, { replace: true });
    },
    [navigate, uploadQueuedChatRows],
  );

  const {
    chatMessages,
    setChatMessages,
    isStreaming,
    connectionLost,
    setCurrentConversationId,
    send,
    stop,
    retry,
    editAndResend,
    regenerate,
    continueFromPartial,
    cancel,
    clearChat,
  } = useSSEChat({ onConversationCreated: handleConversationCreated });

  // Leaving a brand-new chat without sending abandons its deferred
  // attachments: when the chat id appears (navigation into a real
  // conversation), drop queued null-scope rows so they can't be flushed into
  // a *different* conversation later. The send path flushes them before this
  // runs, so the just-handed-over rows are already gone — a no-op there.
  // Staying on the new chat (or returning to it) keeps the draft's rows.
  const previousConversationIdRef = useRef<string | null>(conversationId);
  useEffect(() => {
    const previous = previousConversationIdRef.current;
    previousConversationIdRef.current = conversationId;
    if (previous === null && conversationId !== null) {
      discardQueuedNewChatRows();
    }
    // When switching to new chat or between different conversations while not streaming,
    // clear the previous conversation's messages so we don't flash old chat content
    if (conversationId === null && !isStreaming) {
      clearChat();
    } else if (
      previous !== null &&
      conversationId !== null &&
      previous !== conversationId &&
      !isStreaming
    ) {
      setChatMessages([]);
    }
  }, [conversationId, discardQueuedNewChatRows, isStreaming, setChatMessages, clearChat]);

  // Keep hook conversationId in sync with props
  useEffect(() => {
    setCurrentConversationId(conversationId);
  }, [conversationId, setCurrentConversationId]);

  // Reconcile messages with SSE chat state
  useEffect(() => {
    // If a response is actively streaming, keep the in-flight SSE message state
    if (isStreaming) {
      return;
    }

    if (messagesData) {
      const flat = messagesData.pages.flatMap((page) => page.messages);
      const mapped = flat.map((m) => {
        // Map tool calls format
        const tcs = Array.isArray(m.tool_calls)
          ? (m.tool_calls as Record<string, unknown>[]).map((tc) => {
              const func = tc["function"] as Record<string, unknown> | undefined;
              return {
                id: String(tc["id"] || tc["tool_call_id"] || Math.random().toString()),
                name: String(tc["name"] || func?.["name"] || "unknown"),
                arguments: (tc["arguments"] || func?.["arguments"] || {}) as Record<
                  string,
                  unknown
                >,
                result: tc["result"] || tc["output"],
                status: (tc["status"] || "done") as "running" | "done" | "failed",
              };
            })
          : [];

        return {
          id: m.id,
          role: m.role,
          content: m.content || "",
          citations: m.citations || [],
          status: m.status || "completed",
          toolCalls: tcs,
          created_at: m.created_at,
        };
      });

      // Sort chronological ascending
      mapped.sort((a, b) => new Date(a.created_at!).getTime() - new Date(b.created_at!).getTime());

      setChatMessages((prev) => {
        // Prevent stale server cache from temporarily wiping out freshly completed in-memory messages
        // while the background query refetch is in-flight.
        if (mapped.length < prev.length) {
          return prev;
        }
        return mapped;
      });
    } else if (!conversationId) {
      clearChat();
    }
  }, [messagesData, conversationId, setChatMessages, clearChat, isStreaming]);

  const handleSend = (text: string) => {
    send(text, { conversationId });
  };

  const handleSelectExample = (prompt: string) => {
    handleSend(prompt);
  };

  // Window-level Drag and Drop events
  const handleWindowDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDraggingWindow) setIsDraggingWindow(true);
  };

  const handleWindowDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only turn off if leaving main container
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDraggingWindow(false);
  };

  const handleWindowDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingWindow(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setWindowDroppedFiles(Array.from(e.dataTransfer.files));
    }
  };

  const formatModelName = (raw?: string | null): string | undefined => {
    if (!raw) return undefined;
    return raw
      .split(/[-_]/)
      .map((w) => (/^\d+(\.\d+)*$/.test(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
      .join(" ");
  };

  const activeTitle = activeConv?.title || "New Chat";
  const activeModel = formatModelName(activeConv?.settings?.model);

  return (
    <div
      onDragOver={handleWindowDragOver}
      onDragLeave={handleWindowDragLeave}
      onDrop={handleWindowDrop}
      className="flex-1 flex flex-col h-full w-full overflow-hidden relative bg-[var(--bg-primary)] transition-colors"
    >
      {/* Visual drag-and-drop feedback overlay */}
      {isDraggingWindow && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center border-2 border-dashed border-[var(--accent-primary)]/50 bg-[var(--bg-primary)]/88 backdrop-blur-xs pointer-events-none animate-enter">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/12 text-[var(--accent-primary)] animate-bounce">
            <Upload size={30} />
          </div>
          <h3 className="mb-1 text-base font-semibold text-[var(--text-primary)]">
            Drop files here to attach
          </h3>
          <p className="text-xs text-[var(--text-secondary)]">
            Files will be uploaded and attached to your next prompt
          </p>
        </div>
      )}

      {/* Top Header toolbar */}
      <ChatToolbar title={activeTitle} model={activeModel} connectionLost={connectionLost} />

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-hidden flex flex-col h-full w-full">
        {isLoading && chatMessages.length === 0 && !isStreaming ? (
          <div className="flex-1 flex flex-col gap-6 p-8 max-w-[860px] mx-auto w-full pt-16 select-none">
            <div className="flex items-center gap-3">
              <Skeleton className="h-8 w-8 rounded-full bg-[var(--bg-tertiary)]" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-4 w-1/4" />
                <Skeleton className="h-4 w-3/4" />
              </div>
            </div>
            <div className="flex items-center gap-3 flex-row-reverse">
              <Skeleton className="h-8 w-8 rounded-full bg-[var(--bg-tertiary)]" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-4 w-1/4 ml-auto" />
                <Skeleton className="h-4 w-2/3 ml-auto" />
              </div>
            </div>
          </div>
        ) : error && chatMessages.length === 0 && !isStreaming ? (
          <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-red-500 select-none">
            <AlertCircle size={24} className="mb-2" />
            <p className="text-xs font-semibold">Failed to load message history.</p>
          </div>
        ) : chatMessages.length === 0 ? (
          <EmptyChat onSelectPrompt={handleSelectExample} />
        ) : (
          <MessageList
            messages={chatMessages}
            onRetry={retry}
            isStreaming={isStreaming}
            onEditPrompt={editAndResend}
            onRegenerate={regenerate}
            onSelectCitation={(citation) => {
              setActiveCitation(citation);
              setIsCitationDrawerOpen(true);
            }}
          />
        )}
      </div>

      {/* Slide-over Citation Details Drawer */}
      <CitationDrawer
        citation={activeCitation}
        isOpen={isCitationDrawerOpen}
        onClose={() => setIsCitationDrawerOpen(false)}
      />

      {/* Connection recovery popup */}
      {connectionLost && (
        <div className="absolute bottom-28 left-1/2 -translate-x-1/2 px-4 md:px-6 w-full max-w-3xl z-20">
          <StreamingRecovery
            onRetry={retry}
            onContinue={continueFromPartial}
            onCancel={cancel}
            hasPartialContent={Boolean(chatMessages[chatMessages.length - 1]?.content?.trim())}
          />
        </div>
      )}

      {/* Fixed bottom input wrapper — the conversation's chat-scoped files sit
          above the composer as removable chips, then the composer itself. */}
      <div
        className="w-full flex-shrink-0 flex justify-center z-10 pt-10 pb-5"
        style={{
          background:
            "linear-gradient(to top, var(--bg-primary) 0%, var(--bg-primary) 65%, transparent 100%)",
        }}
      >
        <div className="flex w-full flex-col items-center gap-2.5">
          <ConversationDocumentChips conversationId={conversationId} />
          <ChatInput
            conversationId={conversationId}
            onSend={handleSend}
            onStop={stop}
            isStreaming={isStreaming}
            droppedFiles={windowDroppedFiles}
          />
        </div>
      </div>
    </div>
  );
};
export default ChatWindow;
