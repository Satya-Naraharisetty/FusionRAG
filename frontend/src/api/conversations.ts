import api from "./client";
import { Conversation, Message } from "../types";

export interface ConversationsListResponse {
  items: Conversation[];
  conversations: Conversation[];
  limit: number;
  next_cursor?: string | null;
  prev_cursor?: string | null;
  has_next_page: boolean;
  has_prev_page: boolean;
  has_more: boolean;
}

export interface MessagesListResponse {
  items: Message[];
  messages: Message[];
  limit: number;
  next_cursor?: string | null;
  prev_cursor?: string | null;
  has_next_page: boolean;
  has_prev_page: boolean;
  has_more: boolean;
}

export const conversationsApi = {
  listConversations(
    limit = 20,
    cursor?: string | null
  ): Promise<ConversationsListResponse> {
    const params: Record<string, any> = { limit };
    if (cursor) params.cursor = cursor;

    return api.get<ConversationsListResponse>("/conversations", { params });
  },

  getConversation(id: string): Promise<Conversation> {
    return api.get<Conversation>(`/conversations/${id}`);
  },

  patchConversation(
    id: string,
    payload: { title?: string; settings?: Partial<Conversation["settings"]> }
  ): Promise<Conversation> {
    return api.patch<Conversation>(`/conversations/${id}`, payload);
  },

  deleteConversation(id: string): Promise<void> {
    return api.delete(`/conversations/${id}`);
  },

  listMessages(
    id: string,
    limit = 50,
    cursor?: string | null
  ): Promise<MessagesListResponse> {
    const params: Record<string, any> = { limit };
    if (cursor) params.cursor = cursor;

    return api.get<MessagesListResponse>(`/conversations/${id}/messages`, {
      params,
    });
  },

  deleteMessagesFrom(
    id: string,
    messageId: string
  ): Promise<{ deleted_count: number }> {
    return api.delete<{ deleted_count: number }>(
      `/conversations/${id}/messages/${messageId}`
    );
  },
};

