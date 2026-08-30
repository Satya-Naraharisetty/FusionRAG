import api from "./client";
import { Conversation, Message } from "../types";

export interface ConversationsListResponse {
  conversations: Conversation[];
  limit: number;
  offset: number;
}

export interface MessagesListResponse {
  messages: Message[];
  limit: number;
  offset: number;
}

export const conversationsApi = {
  listConversations(limit = 20, offset = 0): Promise<ConversationsListResponse> {
    return api.get<ConversationsListResponse>("/conversations", {
      params: { limit, offset },
    });
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

  listMessages(id: string, limit = 50, offset = 0): Promise<MessagesListResponse> {
    return api.get<MessagesListResponse>(`/conversations/${id}/messages`, {
      params: { limit, offset },
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

