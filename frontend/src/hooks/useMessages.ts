import { useInfiniteQuery } from "@tanstack/react-query";
import { conversationsApi } from "../api/conversations";
import { QUERY_KEYS } from "../lib/constants";

export const useMessages = (conversationId: string | null, limit = 50) => {
  return useInfiniteQuery({
    queryKey: [QUERY_KEYS.MESSAGES, conversationId],
    queryFn: ({ pageParam = null }: { pageParam?: string | null }) => {
      if (!conversationId) return Promise.reject("No conversation ID");
      return conversationsApi.listMessages(conversationId, limit, pageParam);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => {
      if (lastPage.has_next_page && lastPage.next_cursor) {
        return lastPage.next_cursor;
      }
      return undefined;
    },
    getPreviousPageParam: (firstPage) => {
      if (firstPage.has_prev_page && firstPage.prev_cursor) {
        return firstPage.prev_cursor;
      }
      return undefined;
    },
    enabled: !!conversationId,
  });
};
