import api, { createSSEStream } from "./client";
import { SSEEvent } from "../types";

export interface ChatRequest {
  question: string;
  conversation_id?: string | null;
  document_ids?: string[] | null;
  top_k?: number | null;
  filters?: Record<string, unknown> | null;
  stream?: boolean;
}

export interface AnswerResponse {
  answer: string;
  citations: Array<{
    document_id: string;
    document_name: string;
    chunk_id: string;
    chunk_index: number;
  }>;
  retrieval_time_ms: number;
  generation_time_ms: number;
  total_time_ms: number;
  model: string;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  conversation_id: string;
  diagnostics?: {
    rewritten: boolean;
    retrieval_skipped: boolean;
    dense_count: number;
    sparse_count: number;
    fusion_count: number;
    rerank_count: number;
    latencies: Record<string, number>;
  };
}

export const chatApi = {
  sendChat(payload: ChatRequest): Promise<AnswerResponse> {
    return api.post<AnswerResponse>("/chat", {
      ...payload,
      stream: false,
    });
  },

  streamChat(payload: ChatRequest, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
    return createSSEStream(
      "/chat",
      {
        ...payload,
        stream: true,
      },
      signal,
    );
  },
};
