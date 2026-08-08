import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMessages } from "../../hooks/useMessages";
import { useSSEChat } from "../../hooks/useSSEChat";
import { useConversation } from "../../hooks/useConversations";
import { EmptyChat } from "./EmptyChat";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { ChatToolbar } from "./ChatToolbar";
import { StreamingRecovery } from "./StreamingRecovery";
import { Skeleton } from "../ui/skeleton";
import { AlertCircle, Upload } from "lucide-react";

interface ChatWindowProps {
  conversationId: string | null;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ conversationId }) => {
  const navigate = useNavigate();
  const { data: messagesData, isLoading, error } = useMessages(conversationId);
  const { data: activeConv } = useConversation(conversationId);
  const [isDraggingWindow, setIsDraggingWindow] = useState(false);
  const [windowDroppedFiles, setWindowDroppedFiles] = useState<File[]>([]);

  const {
    chatMessages,
    setChatMessages,
    isStreaming,
    connectionLost,
    currentConversationId,
    setCurrentConversationId,
    send,
    stop,
    retry,
    continueFromPartial,
    cancel,
    clearChat,
  } = useSSEChat();

  // Sync URL when a new conversation is created
  useEffect(() => {
    if (currentConversationId && currentConversationId !== conversationId) {
      navigate(`/chat/${currentConversationId}`, { replace: true });
    }
  }, [currentConversationId, conversationId, navigate]);

  // Set conversationId context inside hook on mount/change
  useEffect(() => {
    setCurrentConversationId(conversationId);
  }, [conversationId, setCurrentConversationId]);

  // Reconcile messages with SSE chat state
  useEffect(() => {
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
                arguments: (tc["arguments"] || func?.["arguments"] || {}) as Record<string, unknown>,
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
      setChatMessages(mapped);
    } else if (!conversationId) {
      clearChat();
    }
  }, [messagesData, conversationId, setChatMessages, clearChat]);

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

  const activeTitle = activeConv?.title || "New Chat";
  const activeModel = activeConv?.settings?.model || "Hybrid RAG v1";

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
          <h3 className="mb-1 text-base font-semibold text-[var(--text-primary)]">Drop files here to attach</h3>
          <p className="text-xs text-[var(--text-secondary)]">Files will be uploaded and attached to your next prompt</p>
        </div>
      )}

      {/* Top Header toolbar */}
      <ChatToolbar
        title={activeTitle}
        model={activeModel}
        connectionLost={connectionLost}
      />

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-hidden flex flex-col h-full w-full">
        {isLoading ? (
          <div className="flex-1 flex flex-col gap-6 p-8 max-w-[780px] mx-auto w-full pt-16 select-none">
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
        ) : error ? (
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
          />
        )}
      </div>

      {/* Connection recovery popup */}
      {connectionLost && (
        <div className="absolute bottom-28 left-1/2 -translate-x-1/2 px-4 md:px-6 w-full max-w-3xl z-20">
          <StreamingRecovery
            onRetry={retry}
            onContinue={continueFromPartial}
            onCancel={cancel}
          />
        </div>
      )}

      {/* Fixed bottom input wrapper */}
      <div className="w-full flex-shrink-0 flex justify-center z-10 pt-10 pb-5"
        style={{ background: "linear-gradient(to top, var(--bg-primary) 0%, var(--bg-primary) 65%, transparent 100%)" }}
      >
        <ChatInput
          conversationId={conversationId}
          onSend={handleSend}
          onStop={stop}
          isStreaming={isStreaming}
          droppedFiles={windowDroppedFiles}
        />
      </div>
    </div>
  );
};
export default ChatWindow;

