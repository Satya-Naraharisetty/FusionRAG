import { useState, useRef, useCallback } from "react";
import { chatApi, ChatRequest } from "../api/chat";
import { ChatMessage, Citation } from "../types";
import { useQueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "../lib/constants";

interface StreamError {
  code: string;
  message: string;
}

export const useSSEChat = () => {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<StreamError | null>(null);
  const [connectionLost, setConnectionLost] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const lastQuestionRef = useRef<string>("");
  const lastDocIdsRef = useRef<string[] | null>(null);
  const lastTopKRef = useRef<number | null>(null);
  const lastFiltersRef = useRef<Record<string, unknown> | null>(null);

  const queryClient = useQueryClient();

  const stop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
      
      // Update last message status to interrupted when stopped by user — the
      // backend persists the partial answer with the same INTERRUPTED status.
      setChatMessages((prev) => {
        if (prev.length === 0) return prev;
        const last = prev[prev.length - 1];
        if (last.role === "assistant" && last.status !== "completed") {
          return [
            ...prev.slice(0, -1),
            { ...last, status: "interrupted" as const },
          ];
        }
        return prev;
      });

      // Invalidate queries to sync with backend db which is finalized by abort
      if (currentConversationId) {
        queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.MESSAGES, currentConversationId] });
      }
    }
  }, [currentConversationId, queryClient]);

  const send = useCallback(
    async (
      question: string,
      opts?: {
        conversationId?: string | null;
        documentIds?: string[] | null;
        topK?: number | null;
        filters?: Record<string, unknown> | null;
      }
    ) => {
      if (isStreaming) return;

      const conversationId = opts?.conversationId ?? currentConversationId;
      const documentIds = opts?.documentIds ?? null;
      const topK = opts?.topK ?? null;
      const filters = opts?.filters ?? null;

      // Save parameters for retry
      lastQuestionRef.current = question;
      lastDocIdsRef.current = documentIds;
      lastTopKRef.current = topK;
      lastFiltersRef.current = filters;

      setStreamError(null);
      setConnectionLost(false);
      setIsStreaming(true);

      // Streamed messages need stable ids so list rendering stays keyed
      // (and message actions like reactions can reference them).
      const newClientMessageId = () =>
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `msg-${Date.now()}-${Math.random().toString(36).slice(2)}`;

      const userMsg: ChatMessage = {
        id: newClientMessageId(),
        role: "user" as const,
        content: question,
        created_at: new Date().toISOString(),
      };

      const assistantMsg: ChatMessage = {
        id: newClientMessageId(),
        role: "assistant" as const,
        content: "",
        status: "pending" as const,
        citations: [],
        toolCalls: [],
        created_at: new Date().toISOString(),
      };

      setChatMessages((prev) => [...prev, userMsg, assistantMsg]);

      abortControllerRef.current = new AbortController();

      const chatPayload: ChatRequest = {
        question,
        conversation_id: conversationId,
        document_ids: documentIds,
        top_k: topK,
        filters,
      };

      try {
        const stream = chatApi.streamChat(chatPayload, abortControllerRef.current.signal);

        for await (const event of stream) {
          const { event: eventType, data } = event;

          if (eventType === "metadata") {
            const conversation_id = data.conversation_id as string;
            setCurrentConversationId(conversation_id);
            
            setChatMessages((prev) => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  citations: (data.citations as Citation[]) || [],
                  status: "streaming" as const,
                },
              ];
            });
          } else if (eventType === "text") {
            const textDelta = data.text as string;
            setChatMessages((prev) => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  content: last.content + textDelta,
                  status: "streaming" as const,
                },
              ];
            });
          } else if (eventType === "tool_call_started") {
            const tc = {
              id: data.id as string,
              name: data.name as string,
              arguments: (data.arguments as Record<string, unknown>) || {},
              status: "running" as const,
            };
            setChatMessages((prev) => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              const updatedToolCalls = [...(last.toolCalls || []), tc];
              return [
                ...prev.slice(0, -1),
                { ...last, toolCalls: updatedToolCalls },
              ];
            });
          } else if (eventType === "tool_call_completed") {
            const toolCallId = data.id as string;
            const toolResult = data.result;
            setChatMessages((prev) => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              const updatedToolCalls = (last.toolCalls || []).map((tc) =>
                tc.id === toolCallId
                  ? { ...tc, result: toolResult, status: "done" as const }
                  : tc
              );
              return [
                ...prev.slice(0, -1),
                { ...last, toolCalls: updatedToolCalls },
              ];
            });
          } else if (eventType === "done") {
            const conversation_id = data.conversation_id as string;
            setCurrentConversationId(conversation_id);
            setChatMessages((prev) => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  content: (data.answer as string) || last.content,
                  citations: (data.citations as Citation[]) || last.citations,
                  status: "completed" as const,
                },
              ];
            });

            // Refresh message history and sidebar list on TanStack Query
            queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.MESSAGES, conversation_id] });
            queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS] });
            setIsStreaming(false);
          } else if (eventType === "error") {
            const errCode = (data.code as string) || "UNKNOWN_ERROR";
            const errMsg = (data.message as string) || "Generation failed";
            setStreamError({ code: errCode, message: errMsg });
            setChatMessages((prev) => {
              if (prev.length === 0) return prev;
              const last = prev[prev.length - 1];
              return [
                ...prev.slice(0, -1),
                { ...last, status: "failed" as const, error: errMsg },
              ];
            });
            setIsStreaming(false);
          }
        }

        // The stream ended without a terminal event (done/error) — e.g. the
        // server closed it after detecting a disconnect. Reflect the persisted
        // INTERRUPTED status so the cursor stops instead of spinning forever.
        setChatMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (
            last.role === "assistant" &&
            (last.status === "pending" || last.status === "streaming")
          ) {
            return [
              ...prev.slice(0, -1),
              { ...last, status: "interrupted" as const },
            ];
          }
          return prev;
        });
        setIsStreaming(false);
      } catch (err: unknown) {
        setIsStreaming(false);
        const isAbort = err instanceof DOMException && err.name === "AbortError";
        if (isAbort) return;

        // Connection dropped or fetch failed
        setConnectionLost(true);
        setChatMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          return [
            ...prev.slice(0, -1),
            { ...last, status: "failed" as const, error: "Network stream disconnected." },
          ];
        });
      }
    },
    [currentConversationId, isStreaming, queryClient]
  );

  const retry = useCallback(() => {
    if (lastQuestionRef.current) {
      // Remove last failed assistant message and the user question, then send again
      setChatMessages((prev) => {
        if (prev.length < 2) return prev;
        return prev.slice(0, -2);
      });
      send(lastQuestionRef.current, {
        conversationId: currentConversationId,
        documentIds: lastDocIdsRef.current,
        topK: lastTopKRef.current,
        filters: lastFiltersRef.current,
      });
    }
  }, [send, currentConversationId]);

  const continueFromPartial = useCallback(() => {
    // Re-send original question but prompt LLM to continue writing
    if (lastQuestionRef.current && chatMessages.length > 0) {
      const last = chatMessages[chatMessages.length - 1];
      const partialText = last.content;
      
      // Remove last failed assistant message
      setChatMessages((prev) => {
        if (prev.length === 0) return prev;
        return prev.slice(0, -1);
      });

      // Prepend context to instruction
      const followUp = `Here is the partial response generated so far: "${partialText}". Please continue generating the response from exactly where it left off without repeating the text.`;
      
      send(followUp, {
        conversationId: currentConversationId,
        documentIds: lastDocIdsRef.current,
        topK: lastTopKRef.current,
        filters: lastFiltersRef.current,
      });
    }
  }, [chatMessages, send, currentConversationId]);

  const cancel = useCallback(() => {
    setStreamError(null);
    setConnectionLost(false);
    // Mark last message as interrupted (partial output preserved)
    setChatMessages((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      return [
        ...prev.slice(0, -1),
        { ...last, status: "interrupted" as const },
      ];
    });
  }, []);

  const clearChat = useCallback(() => {
    setChatMessages([]);
    setCurrentConversationId(null);
    setStreamError(null);
    setConnectionLost(false);
  }, []);

  return {
    chatMessages,
    setChatMessages,
    isStreaming,
    streamError,
    connectionLost,
    currentConversationId,
    setCurrentConversationId,
    send,
    stop,
    retry,
    continueFromPartial,
    cancel,
    clearChat,
  };
};
