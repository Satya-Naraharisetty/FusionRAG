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
  async listConversations(limit = 20, offset = 0): Promise<ConversationsListResponse> {
    const response = await api.get<ConversationsListResponse>("/conversations", {
      params: { limit, offset },
    });
    return response.data;
  },

  async getConversation(id: string): Promise<Conversation> {
    const response = await api.get<Conversation>(`/conversations/${id}`);
    return response.data;
  },

  async patchConversation(
    id: string,
    payload: { title?: string; settings?: Partial<Conversation["settings"]> }
  ): Promise<Conversation> {
    const response = await api.patch<Conversation>(`/conversations/${id}`, payload);
    return response.data;
  },

  async deleteConversation(id: string): Promise<void> {
    await api.delete(`/conversations/${id}`);
  },

  async listMessages(id: string, limit = 50, offset = 0): Promise<MessagesListResponse> {
    const response = await api.get<MessagesListResponse>(`/conversations/${id}/messages`, {
      params: { limit, offset },
    });
    return response.data;
  },
};
