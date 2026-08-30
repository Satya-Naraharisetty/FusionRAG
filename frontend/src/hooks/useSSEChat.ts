import { useState, useRef, useCallback } from "react";
import { chatApi, ChatRequest } from "../api/chat";
import { conversationsApi, MessagesListResponse } from "../api/conversations";
import { ChatMessage, Citation } from "../types";
import { InfiniteData, useQueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "../lib/constants";
import { maybeNotifyStreamComplete } from "../lib/notifications";

interface StreamError {
  code: string;
  message: string;
}

export interface UseSSEChatOptions {
  onConversationCreated?: (conversationId: string) => void;
}

export const useSSEChat = (options?: UseSSEChatOptions) => {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<StreamError | null>(null);
  const [connectionLost, setConnectionLost] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);

  const onConversationCreatedRef = useRef(options?.onConversationCreated);
  onConversationCreatedRef.current = options?.onConversationCreated;

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
        truncateFromMessageId?: string | null;
        deleteBeforeStreamMessageId?: string | null;
      }
    ) => {
      if (isStreaming) return;

      const conversationId = opts?.conversationId ?? currentConversationId;
      const documentIds = opts?.documentIds ?? null;
      const topK = opts?.topK ?? null;
      const filters = opts?.filters ?? null;
      const truncateFromMessageId = opts?.truncateFromMessageId ?? null;
      const deleteBeforeStreamMessageId = opts?.deleteBeforeStreamMessageId ?? null;

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

      const assistantId = newClientMessageId();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant" as const,
        content: "",
        status: "pending" as const,
        citations: [],
        toolCalls: [],
        created_at: new Date().toISOString(),
      };

      setChatMessages((prev) => {
        let base = prev;
        if (truncateFromMessageId) {
          const targetIdx = prev.findIndex((m) => m.id === truncateFromMessageId);
          if (targetIdx !== -1) {
            base = prev.slice(0, targetIdx);
          }
        }
        return [...base, userMsg, assistantMsg];
      });

      // Safe updater helper that targets the specific assistant message by id
      // and guarantees that user messages are never mutated or overwritten.
      const updateAssistant = (updater: (msg: ChatMessage) => ChatMessage) => {
        setChatMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === assistantId);
          if (idx !== -1) {
            const next = [...prev];
            next[idx] = updater(next[idx]);
            return next;
          }
          const lastAssistantIdx = prev.map((m) => m.role).lastIndexOf("assistant");
          if (lastAssistantIdx !== -1) {
            const next = [...prev];
            next[lastAssistantIdx] = updater(next[lastAssistantIdx]);
            return next;
          }
          return [...prev, updater(assistantMsg)];
        });
      };

      // If this is an edit resend, delete old messages on the backend before opening the stream
      // to guarantee Postgres doesn't delete the newly created message in a race condition.
      if (deleteBeforeStreamMessageId && conversationId) {
        try {
          await conversationsApi.deleteMessagesFrom(conversationId, deleteBeforeStreamMessageId);
        } catch (err) {
          console.error("Failed to delete messages before stream:", err);
        }
      }

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
            if (!conversationId && conversation_id) {
              onConversationCreatedRef.current?.(conversation_id);
            }
            setCurrentConversationId(conversation_id);

            const diagnostics = data.diagnostics as
              | { retrieval_skipped?: boolean }
              | undefined;

            updateAssistant((msg) => ({
              ...msg,
              citations: (data.citations as Citation[]) || [],
              retrievalSkipped: diagnostics?.retrieval_skipped ?? false,
              status: "streaming" as const,
            }));
          } else if (eventType === "text") {
            const textDelta = data.text as string;
            updateAssistant((msg) => ({
              ...msg,
              content: msg.content + textDelta,
              status: "streaming" as const,
            }));
          } else if (eventType === "tool_call_started") {
            const tc = {
              id: data.id as string,
              name: data.name as string,
              arguments: (data.arguments as Record<string, unknown>) || {},
              status: "running" as const,
            };
            updateAssistant((msg) => ({
              ...msg,
              toolCalls: [...(msg.toolCalls || []), tc],
            }));
          } else if (eventType === "tool_call_completed") {
            const toolCallId = data.id as string;
            const toolResult = data.result;
            updateAssistant((msg) => ({
              ...msg,
              toolCalls: (msg.toolCalls || []).map((tc) =>
                tc.id === toolCallId
                  ? { ...tc, result: toolResult, status: "done" as const }
                  : tc
              ),
            }));
          } else if (eventType === "done") {
            const conversation_id = data.conversation_id as string;
            if (!conversationId && conversation_id) {
              onConversationCreatedRef.current?.(conversation_id);
            }
            setCurrentConversationId(conversation_id);

            // Fire configured completion alerts (desktop notification / chime)
            const answer = (data.answer as string) || "";
            if (answer) {
              maybeNotifyStreamComplete({
                title: "Response ready",
                body: answer.length > 80 ? `${answer.slice(0, 80)}…` : answer,
              });
            }

            const doneDiagnostics = data.diagnostics as
              | { retrieval_skipped?: boolean }
              | undefined;

            updateAssistant((msg) => ({
              ...msg,
              content: (data.answer as string) || msg.content,
              citations: (data.citations as Citation[]) || msg.citations,
              retrievalSkipped:
                doneDiagnostics?.retrieval_skipped ?? msg.retrievalSkipped ?? false,
              status: "completed" as const,
            }));

            // Refresh message history and sidebar list on TanStack Query
            queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.MESSAGES, conversation_id] });
            queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS] });
            setIsStreaming(false);
          } else if (eventType === "error") {
            const errCode = (data.code as string) || "UNKNOWN_ERROR";
            const errMsg = (data.message as string) || "Generation failed";
            setStreamError({ code: errCode, message: errMsg });
            updateAssistant((msg) => ({
              ...msg,
              status: "failed" as const,
              error: errMsg,
            }));
            setIsStreaming(false);
          }
        }

        // The stream ended without a terminal event (done/error) — e.g. the
        // server closed it after detecting a disconnect. Reflect the persisted
        // INTERRUPTED status so the cursor stops instead of spinning forever.
        updateAssistant((msg) => {
          if (msg.status === "pending" || msg.status === "streaming") {
            return { ...msg, status: "interrupted" as const };
          }
          return msg;
        });
        setIsStreaming(false);
      } catch (err: unknown) {
        setIsStreaming(false);
        const isAbort = err instanceof DOMException && err.name === "AbortError";
        if (isAbort) return;

        // Connection dropped or fetch failed
        setConnectionLost(true);
        updateAssistant((msg) => ({
          ...msg,
          status: "failed" as const,
          error: "Network stream disconnected.",
        }));
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
      const partialText = last?.content?.trim() || "";

      if (!partialText) {
        retry();
        return;
      }
      
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
  }, [chatMessages, retry, send, currentConversationId]);

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

  const editAndResend = useCallback(
    (messageId: string, newText: string) => {
      if (isStreaming || !newText.trim()) return;

      const convId = currentConversationId;

      // 1. Immediately prune the query cache so any background query refetch won't have stale messages
      if (convId) {
        queryClient.setQueryData<InfiniteData<MessagesListResponse>>(
          [QUERY_KEYS.MESSAGES, convId],
          (oldData) => {
            if (!oldData?.pages) return oldData;
            return {
              ...oldData,
              pages: oldData.pages.map((page) => {
                const msgs = page.messages || [];
                const targetIdx = msgs.findIndex((m) => m.id === messageId);
                if (targetIdx === -1) return page;
                return {
                  ...page,
                  messages: msgs.slice(0, targetIdx),
                };
              }),
            };
          }
        );
      }

      // 2. Atomically truncate and start streaming the new message (backend delete completes before stream request)
      send(newText.trim(), {
        conversationId: convId,
        truncateFromMessageId: messageId,
        deleteBeforeStreamMessageId: messageId,
      });
    },
    [isStreaming, send, currentConversationId, queryClient]
  );

  const regenerate = useCallback(
    (assistantMessageId?: string) => {
      if (isStreaming) return;
      let promptText = lastQuestionRef.current;

      setChatMessages((prev) => {
        if (prev.length === 0) return prev;
        let idx = -1;
        if (assistantMessageId) {
          idx = prev.findIndex((m) => m.id === assistantMessageId);
        }
        if (idx === -1) {
          idx = prev.map((m) => m.role).lastIndexOf("assistant");
        }
        if (idx > 0 && prev[idx - 1]?.role === "user") {
          promptText = prev[idx - 1].content;
          // Remove the assistant message and subsequent items, keeping up to user message
          return prev.slice(0, idx);
        }
        if (prev.length >= 2) {
          return prev.slice(0, -1);
        }
        return prev;
      });

      if (promptText) {
        send(promptText, {
          conversationId: currentConversationId,
          documentIds: lastDocIdsRef.current,
          topK: lastTopKRef.current,
          filters: lastFiltersRef.current,
        });
      }
    },
    [isStreaming, send, currentConversationId]
  );

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
    editAndResend,
    regenerate,
    continueFromPartial,
    cancel,
    clearChat,
  };
};

