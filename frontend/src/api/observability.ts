import api from "./client";

export interface DailyMetric {
  date: string;
  tokens: number;
  cost: number;
  avg_latency_ms: number;
}

export interface ObservabilityMetrics {
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost: number;
  avg_total_latency_ms: number;
  avg_retrieval_latency_ms: number;
  avg_generation_latency_ms: number;
  daily_usage: DailyMetric[];
}

export interface TraceItem {
  id: string;
  conversation_id: string;
  question: string;
  answer: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost: number;
  retrieval_time_ms: number | null;
  generation_time_ms: number | null;
  total_time_ms: number | null;
  created_at: string;
  citations_count: number;
}

export interface TraceListResponse {
  total: number;
  items: TraceItem[];
}

export const observabilityApi = {
  getMetrics(): Promise<ObservabilityMetrics> {
    return api.get<ObservabilityMetrics>("/observability/metrics");
  },

  getTraces(limit = 50, offset = 0): Promise<TraceListResponse> {
    return api.get<TraceListResponse>("/observability/traces", {
      params: { limit, offset },
    });
  },
};
