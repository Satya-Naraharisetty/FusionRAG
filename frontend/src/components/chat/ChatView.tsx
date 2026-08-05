import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useMessages } from "../../hooks/useMessages";
import { useSSEChat } from "../../hooks/useSSEChat";
import { EmptyChat } from "./EmptyChat";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { StreamingRecovery } from "./StreamingRecovery";
import { Skeleton } from "../ui/skeleton";
import { AlertCircle } from "lucide-react";

interface ChatViewProps {
  conversationId: string | null;
}

export const ChatView: React.FC<ChatViewProps> = ({ conversationId }) => {
  const navigate = useNavigate();
  const { data: messagesData, isLoading, error } = useMessages(conversationId);
  
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

  // Reconcile infinite Query messages with SSE chat state
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

  return (
    <div className="flex-1 flex flex-col h-full w-full overflow-hidden bg-zinc-950">
      {/* Messages / Welcome list */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {isLoading ? (
          <div className="flex-1 flex flex-col gap-6 p-6 max-w-3xl mx-auto w-full pt-16">
            <div className="flex items-center gap-3">
              <Skeleton className="h-8 w-8 rounded-full bg-zinc-900" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-4 w-1/4 bg-zinc-900" />
                <Skeleton className="h-4 w-3/4 bg-zinc-900" />
              </div>
            </div>
            <div className="flex items-center gap-3 flex-row-reverse">
              <Skeleton className="h-8 w-8 rounded-full bg-zinc-900" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-4 w-1/4 bg-zinc-900 ml-auto" />
                <Skeleton className="h-4 w-2/3 bg-zinc-900 ml-auto" />
              </div>
            </div>
          </div>
        ) : error ? (
          <div className="flex-1 flex flex-col items-center justify-center p-6 text-center text-red-400">
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

      {/* Connection recovery panel */}
      {connectionLost && (
        <div className="px-4 md:px-6 max-w-3xl mx-auto w-full">
          <StreamingRecovery
            onRetry={retry}
            onContinue={continueFromPartial}
            onCancel={cancel}
          />
        </div>
      )}

      {/* Input textbox bar */}
      <ChatInput
        conversationId={conversationId}
        onSend={handleSend}
        onStop={stop}
        isStreaming={isStreaming}
      />
    </div>
  );
};
