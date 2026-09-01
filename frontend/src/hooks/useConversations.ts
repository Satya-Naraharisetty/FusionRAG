import { useContext } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { conversationsApi, ConversationsListResponse } from "../api/conversations";
import { UploadQueueContext } from "../context/UploadQueueContext";
import { QUERY_KEYS } from "../lib/constants";
import { Conversation } from "../types";
import toast from "react-hot-toast";

export const useConversations = (limit = 100, cursor: string | null = null) => {
  return useQuery({
    queryKey: [QUERY_KEYS.CONVERSATIONS, limit, cursor],
    queryFn: () => conversationsApi.listConversations(limit, cursor),
  });
};

export const useConversation = (id: string | null) => {
  return useQuery({
    queryKey: [QUERY_KEYS.CONVERSATIONS, id],
    queryFn: () => (id ? conversationsApi.getConversation(id) : Promise.reject("No ID provided")),
    enabled: !!id,
  });
};

export const useRenameConversation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      conversationsApi.patchConversation(id, { title }),
    onMutate: async ({ id, title }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS] });

      // Snapshot the previous value
      const previousLists = queryClient.getQueriesData<ConversationsListResponse>({
        queryKey: [QUERY_KEYS.CONVERSATIONS],
      });

      // Optimistically update to the new value in all matched conversation list caches
      queryClient.setQueriesData<ConversationsListResponse>(
        { queryKey: [QUERY_KEYS.CONVERSATIONS] },
        (old) => {
          // Guard against list-shaped caches only: setQueriesData's partial key
          // [CONVERSATIONS] also matches the single-conversation cache
          // [CONVERSATIONS, id], whose data is a bare Conversation object with
          // no .conversations array.
          if (!old || !Array.isArray(old.conversations)) return old;
          return {
            ...old,
            conversations: old.conversations.map((c) =>
              c.id === id ? { ...c, title, updated_at: new Date().toISOString() } : c,
            ),
          };
        },
      );

      // Also update single conversation cache
      const previousConv = queryClient.getQueryData<Conversation>([QUERY_KEYS.CONVERSATIONS, id]);
      if (previousConv) {
        queryClient.setQueryData<Conversation>([QUERY_KEYS.CONVERSATIONS, id], {
          ...previousConv,
          title,
          updated_at: new Date().toISOString(),
        });
      }

      return { previousLists, previousConv };
    },
    onError: (_err, variables, context) => {
      // Rollback list cache
      if (context?.previousLists) {
        context.previousLists.forEach(([queryKey, oldData]) => {
          queryClient.setQueryData(queryKey, oldData);
        });
      }
      // Rollback single conversation cache
      if (context?.previousConv) {
        queryClient.setQueryData([QUERY_KEYS.CONVERSATIONS, variables.id], context.previousConv);
      }
      toast.error("Failed to rename conversation.");
    },
    onSettled: (_data, _error, variables) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS] });
      queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS, variables.id] });
    },
  });
};

export const useDeleteConversation = () => {
  const queryClient = useQueryClient();
  // The upload queue drops chat-scoped rows (and their in-flight uploads) when
  // their conversation is deleted — chat attachments die with their chat. Raw
  // context (not the throwing hook) so callers outside the provider, e.g.
  // isolated tests, degrade gracefully to "no queue to clean".
  const queueContext = useContext(UploadQueueContext);

  return useMutation({
    mutationFn: (id: string) => conversationsApi.deleteConversation(id),
    onMutate: async (id) => {
      queueContext?.discardConversationRows(id);
      await queryClient.cancelQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS] });

      const previousLists = queryClient.getQueriesData<ConversationsListResponse>({
        queryKey: [QUERY_KEYS.CONVERSATIONS],
      });

      // Optimistically delete from conversation lists
      queryClient.setQueriesData<ConversationsListResponse>(
        { queryKey: [QUERY_KEYS.CONVERSATIONS] },
        (old) => {
          // Guard against list-shaped caches only — see useRenameConversation:
          // the partial key also matches the single-conversation cache, whose
          // data has no .conversations array.
          if (!old || !Array.isArray(old.conversations)) return old;
          return {
            ...old,
            conversations: old.conversations.filter((c) => c.id !== id),
          };
        },
      );

      // Remove deleted conversation and its messages from single-conversation query caches
      queryClient.removeQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS, id] });
      queryClient.removeQueries({ queryKey: [QUERY_KEYS.MESSAGES, id] });

      return { previousLists };
    },
    onError: (_err, _id, context) => {
      if (context?.previousLists) {
        context.previousLists.forEach(([queryKey, oldData]) => {
          queryClient.setQueryData(queryKey, oldData);
        });
      }
      toast.error("Failed to delete conversation.");
    },
    onSettled: (_data, _error, id) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS] });
      if (id) {
        queryClient.removeQueries({ queryKey: [QUERY_KEYS.CONVERSATIONS, id] });
        queryClient.removeQueries({ queryKey: [QUERY_KEYS.MESSAGES, id] });
      }
    },
  });
};
