import api, { getAccessToken } from "./client";

export interface EvaluationMetricResult {
  score: number;
  passed: boolean | null;
  reason: string | null;
}

export interface RetrievedContext {
  text: string;
  score: number | null;
}

export interface EvaluationResult {
  sample_id: string;
  question: string;
  expected_answer: string | null;
  actual_answer: string | null;
  latency: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  error_category: string;
  metrics: Record<string, EvaluationMetricResult>;
  retrieved_contexts: RetrievedContext[];
}

export interface EvaluationRun {
  id: string;
  name: string;
  profile: string;
  dataset_id: string;
  dataset_version: string;
  status: string;
  total_samples: number;
  completed_samples: number;
  total_cost: number;
  avg_latency: number;
  created_at: string;
}

export interface StartBenchmarkParams {
  dataset_path: string;
  dataset_id: string;
  version: string;
  profile: string;
  pipelines?: string[];
  mock: boolean;
}

export interface StartBenchmarkResponse {
  message: string;
  run_id: string;
  status: string;
  total_samples: number;
  total_cost: number;
  avg_latency: number;
}

export interface RegressionParams {
  candidate_run_id: string;
  baseline_run_id: string;
  thresholds?: Record<string, number>;
}

export interface RegressionResponse {
  passed: boolean;
  baseline_run_id: string;
  candidate_run_id: string;
  metric_deltas: Record<string, number>;
  details: Record<string, unknown>;
}

export const evaluationApi = {
  getRuns(): Promise<EvaluationRun[]> {
    return api.get<EvaluationRun[]>("/evaluation/runs");
  },

  startBenchmark(params: StartBenchmarkParams): Promise<StartBenchmarkResponse> {
    return api.post<StartBenchmarkResponse>("/evaluation/benchmark", params);
  },

  runRegression(params: RegressionParams): Promise<RegressionResponse> {
    return api.post<RegressionResponse>("/evaluation/regression", params);
  },

  async getReportHtml(runId: string): Promise<string> {
    const token = getAccessToken();
    const apiBase = (import.meta.env.VITE_API_URL || "http://localhost:8000") + "/api/v1";
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(`${apiBase}/evaluation/reports/${runId}?format=html`, {
      headers,
    });
    if (!response.ok) {
      throw new Error(`Failed to load HTML report: ${response.statusText}`);
    }
    return response.text();
  },
};
