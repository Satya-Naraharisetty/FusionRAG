import { useInfiniteQuery } from "@tanstack/react-query";
import { conversationsApi } from "../api/conversations";
import { QUERY_KEYS } from "../lib/constants";

export const useMessages = (conversationId: string | null, limit = 50) => {
  return useInfiniteQuery({
    queryKey: [QUERY_KEYS.MESSAGES, conversationId],
    queryFn: ({ pageParam = 0 }) => {
      if (!conversationId) return Promise.reject("No conversation ID");
      return conversationsApi.listMessages(conversationId, limit, pageParam);
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (lastPage.messages.length < lastPage.limit) {
        return undefined;
      }
      return lastPage.offset + lastPage.limit;
    },
    enabled: !!conversationId,
  });
};
