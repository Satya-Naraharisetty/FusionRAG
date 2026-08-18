import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Play,
  TrendingUp,
  FileText,
  Clock,
  DollarSign,
  Zap,
  Layers,
  RefreshCw,
  Cpu,
  BarChart2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "../components/ui/Button";
import { evaluationApi, EvaluationRun, RegressionResponse } from "../api/evaluation";
import { observabilityApi, TraceItem, DailyMetric } from "../api/observability";
import toast from "react-hot-toast";

export const AdminDashboardPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"observability" | "evaluation">("observability");

  // State for triggers and modals
  const [isRunModalOpen, setIsRunModalOpen] = useState(false);
  const [isCompareModalOpen, setIsCompareModalOpen] = useState(false);
  const [selectedReportRunId, setSelectedReportRunId] = useState<string | null>(null);
  const [reportHtml, setReportHtml] = useState<string>("");
  const [isLoadingReport, setIsLoadingReport] = useState(false);

  // Form states for new run
  const [datasetPath, setDatasetPath] = useState("tests/evaluation/simple_rag_dataset.json");
  const [datasetId, setDatasetId] = useState("simple-rag");
  const [datasetVersion, setDatasetVersion] = useState("1.0.0");
  const [profile, setProfile] = useState("quick");
  const [mockMode, setMockMode] = useState(true);

  // Form states for regression comparison
  const [candidateRunId, setCandidateRunId] = useState("");
  const [baselineRunId, setBaselineRunId] = useState("");
  const [regressionResult, setRegressionResult] = useState<RegressionResponse | null>(null);

  // Trace details expander state
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null);

  // 1. Fetch Observability data
  const {
    data: obMetrics,
    isLoading: isObLoading,
    refetch: refetchOb,
  } = useQuery({
    queryKey: ["observabilityMetrics"],
    queryFn: () => observabilityApi.getMetrics(),
    refetchInterval: 15000, // refresh every 15 seconds
  });

  const {
    data: obTraces,
    isLoading: isTracesLoading,
    refetch: refetchTraces,
  } = useQuery({
    queryKey: ["observabilityTraces"],
    queryFn: () => observabilityApi.getTraces(50, 0),
    refetchInterval: 15000,
  });

  // 2. Fetch Evaluation runs
  const {
    data: evalRuns = [],
    isLoading: isEvalLoading,
    refetch: refetchEval,
  } = useQuery({
    queryKey: ["evaluationRuns"],
    queryFn: () => evaluationApi.getRuns(),
  });

  // Mutate: Trigger Run
  const runMutation = useMutation({
    mutationFn: evaluationApi.startBenchmark,
    onSuccess: (data) => {
      toast.success(`Benchmark started! Run ID: ${data.run_id}`);
      setIsRunModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ["evaluationRuns"] });
    },
    onError: (err: Error) => {
      toast.error(`Failed to launch benchmark: ${err.message || String(err)}`);
    },
  });

  // Mutate: Compare runs
  const compareMutation = useMutation({
    mutationFn: evaluationApi.runRegression,
    onSuccess: (data) => {
      setRegressionResult(data);
      queryClient.invalidateQueries({ queryKey: ["evaluationRuns"] });
    },
    onError: (err: Error) => {
      toast.error(`Regression check failed: ${err.message || String(err)}`);
    },
  });

  // Load HTML Report when run selected
  useEffect(() => {
    if (selectedReportRunId) {
      setIsLoadingReport(true);
      setReportHtml("");
      evaluationApi
        .getReportHtml(selectedReportRunId)
        .then((html) => {
          setReportHtml(html);
        })
        .catch((err) => {
          toast.error("Failed to load report HTML");
          setReportHtml(`<div style="color:red;padding:20px;">Error loading report: ${err.message || err}</div>`);
        })
        .finally(() => {
          setIsLoadingReport(false);
        });
    }
  }, [selectedReportRunId]);

  const handleStartBenchmark = (e: React.FormEvent) => {
    e.preventDefault();
    runMutation.mutate({
      dataset_path: datasetPath,
      dataset_id: datasetId,
      version: datasetVersion,
      profile: profile,
      mock: mockMode,
    });
  };

  const handleCompareRegression = (e: React.FormEvent) => {
    e.preventDefault();
    if (!candidateRunId || !baselineRunId) {
      toast.error("Please select both candidate and baseline runs.");
      return;
    }
    compareMutation.mutate({
      candidate_run_id: candidateRunId,
      baseline_run_id: baselineRunId,
    });
  };

  // Helper: Format Date
  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return dateStr;
    }
  };

  // Helper: Draw SVG Line Chart
  const renderSVGLineChart = (data: DailyMetric[]) => {
    if (!data || data.length === 0) return null;
    const padding = 40;
    const width = 500;
    const height = 180;

    const latencies = data.map((d) => d.avg_latency_ms);
    const maxLat = Math.max(...latencies, 100);
    const minLat = Math.min(...latencies, 0);
    const delta = maxLat - minLat;

    const points = data
      .map((d, index) => {
        const x = padding + (index * (width - padding * 2)) / (data.length - 1);
        const y = height - padding - ((d.avg_latency_ms - minLat) * (height - padding * 2)) / delta;
        return `${x},${y}`;
      })
      .join(" ");

    return (
      <svg className="w-full h-full text-[var(--accent-primary)]" viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent-primary)" stopOpacity="0.2" />
            <stop offset="100%" stopColor="var(--accent-primary)" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        {/* Grid lines */}
        <line x1={padding} y1={padding} x2={width - padding} y2={padding} stroke="var(--border-subtle)" strokeWidth={0.5} strokeDasharray="3 3" />
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border-default)" strokeWidth={1} />
        {/* Y Axis labels */}
        <text x={padding - 5} y={padding + 5} textAnchor="end" fontSize={8} fill="var(--text-muted)">{Math.round(maxLat)}ms</text>
        <text x={padding - 5} y={height - padding + 3} textAnchor="end" fontSize={8} fill="var(--text-muted)">{Math.round(minLat)}ms</text>
        {/* Area fill */}
        {points && (
          <polygon
            points={`${padding},${height - padding} ${points} ${width - padding},${height - padding}`}
            fill="url(#lineGrad)"
          />
        )}
        {/* Line */}
        {points && (
          <polyline
            fill="none"
            stroke="var(--accent-primary)"
            strokeWidth={2}
            points={points}
          />
        )}
        {/* Data points */}
        {data.map((d, index) => {
          const x = padding + (index * (width - padding * 2)) / (data.length - 1);
          const y = height - padding - ((d.avg_latency_ms - minLat) * (height - padding * 2)) / delta;
          return (
            <g key={index} className="group cursor-pointer">
              <circle cx={x} cy={y} r={4} fill="var(--bg-elevated)" stroke="var(--accent-primary)" strokeWidth={2} />
              <title>{d.date}: {d.avg_latency_ms}ms</title>
            </g>
          );
        })}
        {/* X Axis labels */}
        {data.map((d, index) => {
          const x = padding + (index * (width - padding * 2)) / (data.length - 1);
          const shortDate = d.date.substring(5); // MM-DD
          return (
            <text key={index} x={x} y={height - 15} textAnchor="middle" fontSize={8} fill="var(--text-muted)">{shortDate}</text>
          );
        })}
      </svg>
    );
  };

  // Helper: Draw SVG Bar Chart
  const renderSVGBarChart = (data: DailyMetric[]) => {
    if (!data || data.length === 0) return null;
    const padding = 40;
    const width = 500;
    const height = 180;

    const tokens = data.map((d) => d.tokens);
    const maxTokens = Math.max(...tokens, 1000);
    const chartHeight = height - padding * 2;
    const barWidth = Math.max(10, ((width - padding * 2) / data.length) * 0.6);
    const spacing = ((width - padding * 2) / data.length);

    return (
      <svg className="w-full h-full text-[var(--accent-secondary)]" viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent-primary)" />
            <stop offset="100%" stopColor="var(--accent-primary)" stopOpacity="0.4" />
          </linearGradient>
        </defs>
        {/* Grid lines */}
        <line x1={padding} y1={padding} x2={width - padding} y2={padding} stroke="var(--border-subtle)" strokeWidth={0.5} strokeDasharray="3 3" />
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border-default)" strokeWidth={1} />
        {/* Y Axis labels */}
        <text x={padding - 5} y={padding + 5} textAnchor="end" fontSize={8} fill="var(--text-muted)">{Math.round(maxTokens)}</text>
        <text x={padding - 5} y={height - padding + 3} textAnchor="end" fontSize={8} fill="var(--text-muted)">0</text>
        {/* Bars */}
        {data.map((d, index) => {
          const x = padding + index * spacing + (spacing - barWidth) / 2;
          const h = (d.tokens / maxTokens) * chartHeight;
          const y = height - padding - h;
          return (
            <g key={index} className="group cursor-pointer">
              <rect x={x} y={y} width={barWidth} height={h} rx={2} fill="url(#barGrad)" />
              <title>{d.date}: {d.tokens} tokens</title>
            </g>
          );
        })}
        {/* X Axis labels */}
        {data.map((d, index) => {
          const x = padding + index * spacing + spacing / 2;
          const shortDate = d.date.substring(5); // MM-DD
          return (
            <text key={index} x={x} y={height - 15} textAnchor="middle" fontSize={8} fill="var(--text-muted)">{shortDate}</text>
          );
        })}
      </svg>
    );
  };

  return (
    <div className="flex-1 bg-[var(--bg-primary)] p-6 overflow-y-auto text-[var(--text-primary)]">
      {/* Header section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[var(--border-default)] pb-5 mb-6">
        <div>
          <h1 className="text-2xl font-bold font-title flex items-center gap-2.5">
            <Cpu className="text-[var(--accent-primary)] animate-pulse" size={24} />
            <span>Admin Console</span>
          </h1>
          <p className="text-xs text-[var(--text-secondary)] mt-1 font-medium">
            Monitor real-time LLM telemetry, cost budgets, and run pipeline evaluation metrics.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {activeTab === "observability" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                refetchOb();
                refetchTraces();
                toast.success("Telemetry refreshed");
              }}
              className="gap-1.5 h-9"
            >
              <RefreshCw size={13} />
              <span>Refresh Metrics</span>
            </Button>
          ) : (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsCompareModalOpen(true)}
                className="gap-1.5 h-9 border-[var(--border-default)] text-[var(--text-primary)]"
              >
                <Layers size={13} />
                <span>Compare Runs</span>
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={() => setIsRunModalOpen(true)}
                className="gap-1.5 h-9"
              >
                <Play size={13} />
                <span>Trigger Benchmark</span>
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Tabs list */}
      <div className="flex border-b border-[var(--border-subtle)] gap-6 mb-6">
        <button
          onClick={() => setActiveTab("observability")}
          className={`pb-3 font-semibold text-sm transition-colors border-b-2 outline-none cursor-pointer flex items-center gap-2 ${
            activeTab === "observability"
              ? "border-[var(--accent-primary)] text-[var(--text-primary)] font-bold"
              : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          }`}
        >
          <Activity size={15} />
          <span>LLM Observability Console</span>
        </button>
        <button
          onClick={() => setActiveTab("evaluation")}
          className={`pb-3 font-semibold text-sm transition-colors border-b-2 outline-none cursor-pointer flex items-center gap-2 ${
            activeTab === "evaluation"
              ? "border-[var(--accent-primary)] text-[var(--text-primary)] font-bold"
              : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          }`}
        >
          <BarChart2 size={15} />
          <span>RAG Evaluation Suite</span>
        </button>
      </div>

      {/* Observability Tab Panel */}
      {activeTab === "observability" && (
        <div className="space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] p-4 flex items-center gap-4">
              <div className="h-10 w-10 rounded-full bg-[var(--accent-primary)]/10 flex items-center justify-center text-[var(--accent-primary)]">
                <DollarSign size={20} />
              </div>
              <div>
                <p className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">Est. API Cost</p>
                <h3 className="text-xl font-bold mt-0.5">${obMetrics?.total_cost ?? "0.0000"}</h3>
              </div>
            </div>

            <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] p-4 flex items-center gap-4">
              <div className="h-10 w-10 rounded-full bg-[var(--accent-primary)]/10 flex items-center justify-center text-[var(--accent-primary)]">
                <Clock size={20} />
              </div>
              <div>
                <p className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">Avg Latency</p>
                <h3 className="text-xl font-bold mt-0.5">
                  {obMetrics?.avg_total_latency_ms ? `${(obMetrics.avg_total_latency_ms / 1000).toFixed(2)}s` : "0.00s"}
                </h3>
              </div>
            </div>

            <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] p-4 flex items-center gap-4">
              <div className="h-10 w-10 rounded-full bg-[var(--accent-primary)]/10 flex items-center justify-center text-[var(--accent-primary)]">
                <Zap size={20} />
              </div>
              <div>
                <p className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">Total Tokens</p>
                <h3 className="text-xl font-bold mt-0.5">{obMetrics?.total_tokens?.toLocaleString() ?? "0"}</h3>
              </div>
            </div>

            <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] p-4 flex items-center gap-4">
              <div className="h-10 w-10 rounded-full bg-[var(--accent-primary)]/10 flex items-center justify-center text-[var(--accent-primary)]">
                <TrendingUp size={20} />
              </div>
              <div>
                <p className="text-[11px] font-medium text-[var(--text-muted)] uppercase tracking-wider">Total LLM Calls</p>
                <h3 className="text-xl font-bold mt-0.5">{obTraces?.total ?? "0"}</h3>
              </div>
            </div>
          </div>

          {/* Charts section */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] p-5">
              <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4 flex items-center gap-1.5">
                <Activity size={14} className="text-[var(--accent-primary)]" />
                <span>Response Latency Trend (Last 7 Days)</span>
              </h3>
              <div className="h-44 w-full flex items-center justify-center">
                {isObLoading ? (
                  <div className="animate-spin h-5 w-5 border-2 border-[var(--accent-primary)] border-t-transparent rounded-full" />
                ) : obMetrics?.daily_usage?.length ? (
                  renderSVGLineChart(obMetrics.daily_usage)
                ) : (
                  <p className="text-xs text-[var(--text-muted)] font-medium">No latency stats available.</p>
                )}
              </div>
            </div>

            <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] p-5">
              <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4 flex items-center gap-1.5">
                <BarChart2 size={14} className="text-[var(--accent-primary)]" />
                <span>Daily Token Volume (Last 7 Days)</span>
              </h3>
              <div className="h-44 w-full flex items-center justify-center">
                {isObLoading ? (
                  <div className="animate-spin h-5 w-5 border-2 border-[var(--accent-primary)] border-t-transparent rounded-full" />
                ) : obMetrics?.daily_usage?.length ? (
                  renderSVGBarChart(obMetrics.daily_usage)
                ) : (
                  <p className="text-xs text-[var(--text-muted)] font-medium">No token stats available.</p>
                )}
              </div>
            </div>
          </div>

          {/* Latency split detail */}
          {obMetrics && (
            <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] p-5">
              <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">Pipeline Latency Breakdown</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <div className="flex justify-between text-xs text-[var(--text-secondary)] font-medium mb-1">
                    <span>Average Retrieval Time</span>
                    <span>{(obMetrics.avg_retrieval_latency_ms).toFixed(1)}ms</span>
                  </div>
                  <div className="h-2 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[var(--accent-primary)]"
                      style={{
                        width: `${Math.min(
                          100,
                          (obMetrics.avg_retrieval_latency_ms / Math.max(1, obMetrics.avg_total_latency_ms)) * 100
                        )}%`,
                      }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs text-[var(--text-secondary)] font-medium mb-1">
                    <span>Average Generation Time</span>
                    <span>{(obMetrics.avg_generation_latency_ms).toFixed(1)}ms</span>
                  </div>
                  <div className="h-2 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[var(--accent-primary)]"
                      style={{
                        width: `${Math.min(
                          100,
                          (obMetrics.avg_generation_latency_ms / Math.max(1, obMetrics.avg_total_latency_ms)) * 100
                        )}%`,
                      }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs text-[var(--text-secondary)] font-medium mb-1">
                    <span>Total Latency</span>
                    <span>{(obMetrics.avg_total_latency_ms / 1000).toFixed(2)}s</span>
                  </div>
                  <div className="h-2 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div className="h-full bg-[var(--accent-primary)] w-full" />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Trace log Table */}
          <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] overflow-hidden">
            <div className="p-4 border-b border-[var(--border-default)] flex items-center justify-between">
              <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">Live LLM Traces (Latest 50 Runs)</h3>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => {
                  refetchTraces();
                  toast.success("Traces updated");
                }}
                className="text-[var(--accent-primary)] font-semibold text-xs"
              >
                Refresh Log
              </Button>
            </div>

            {isTracesLoading ? (
              <div className="p-8 flex items-center justify-center">
                <div className="animate-spin h-6 w-6 border-2 border-[var(--accent-primary)] border-t-transparent rounded-full" />
              </div>
            ) : obTraces?.items?.length === 0 ? (
              <p className="p-8 text-center text-xs text-[var(--text-muted)] font-medium">No traces recorded yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[var(--bg-tertiary)] border-b border-[var(--border-default)] text-[11px] font-bold text-[var(--text-secondary)] uppercase tracking-wider">
                      <th className="p-3 w-10"></th>
                      <th className="p-3">User Prompt</th>
                      <th className="p-3">Cost</th>
                      <th className="p-3">Tokens</th>
                      <th className="p-3">Latency</th>
                      <th className="p-3">Citations</th>
                      <th className="p-3">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {obTraces?.items.map((trace: TraceItem) => {
                      const isExpanded = expandedTraceId === trace.id;
                      return (
                        <React.Fragment key={trace.id}>
                          <tr className="border-b border-[var(--border-default)] hover:bg-[var(--bg-tertiary)]/30 text-xs transition-colors">
                            <td className="p-3">
                              <button
                                onClick={() => setExpandedTraceId(isExpanded ? null : trace.id)}
                                className="text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
                              >
                                {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                              </button>
                            </td>
                            <td className="p-3 max-w-xs truncate font-medium text-[var(--text-primary)]">{trace.question}</td>
                            <td className="p-3 font-mono">${trace.cost.toFixed(5)}</td>
                            <td className="p-3 font-mono text-[var(--text-secondary)]">
                              in: {trace.prompt_tokens} / out: {trace.completion_tokens}
                            </td>
                            <td className="p-3 font-mono text-[var(--text-secondary)]">
                              {trace.total_time_ms ? `${(trace.total_time_ms / 1000).toFixed(2)}s` : "N/A"}
                            </td>
                            <td className="p-3 font-mono">{trace.citations_count}</td>
                            <td className="p-3 text-[var(--text-muted)]">{formatDate(trace.created_at)}</td>
                          </tr>
                          {isExpanded && (
                            <tr className="bg-[var(--bg-tertiary)]/10 border-b border-[var(--border-default)] text-xs">
                              <td colSpan={7} className="p-4">
                                <div className="space-y-3 font-medium">
                                  <div>
                                    <h4 className="text-[10px] uppercase font-bold text-[var(--text-muted)] tracking-wider">Full Prompt Query:</h4>
                                    <p className="bg-[var(--bg-input)] border border-[var(--border-subtle)] p-2.5 rounded-md mt-1 font-mono text-[11px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">
                                      {trace.question}
                                    </p>
                                  </div>
                                  <div>
                                    <h4 className="text-[10px] uppercase font-bold text-[var(--text-muted)] tracking-wider">Assistant Response:</h4>
                                    <p className="bg-[var(--bg-input)] border border-[var(--border-subtle)] p-2.5 rounded-md mt-1 font-mono text-[11px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">
                                      {trace.answer}
                                    </p>
                                  </div>
                                  <div className="grid grid-cols-3 gap-4 text-[11px]">
                                    <div>
                                      <span className="font-bold text-[var(--text-muted)]">Retrieval Latency: </span>
                                      <span className="font-mono">{trace.retrieval_time_ms ? `${trace.retrieval_time_ms.toFixed(1)}ms` : "N/A"}</span>
                                    </div>
                                    <div>
                                      <span className="font-bold text-[var(--text-muted)]">Generation Latency: </span>
                                      <span className="font-mono">{trace.generation_time_ms ? `${trace.generation_time_ms.toFixed(1)}ms` : "N/A"}</span>
                                    </div>
                                    <div>
                                      <span className="font-bold text-[var(--text-muted)]">Total Response Latency: </span>
                                      <span className="font-mono">{trace.total_time_ms ? `${trace.total_time_ms.toFixed(1)}ms` : "N/A"}</span>
                                    </div>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Evaluations Tab Panel */}
      {activeTab === "evaluation" && (
        <div className="space-y-6">
          {/* Historical Runs List Table */}
          <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] overflow-hidden">
            <div className="p-4 border-b border-[var(--border-default)] flex items-center justify-between">
              <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">Offline Evaluation Runs</h3>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => {
                  refetchEval();
                  toast.success("Benchmark list updated");
                }}
                className="text-[var(--accent-primary)] font-semibold text-xs"
              >
                Reload
              </Button>
            </div>

            {isEvalLoading ? (
              <div className="p-8 flex items-center justify-center">
                <div className="animate-spin h-6 w-6 border-2 border-[var(--accent-primary)] border-t-transparent rounded-full" />
              </div>
            ) : evalRuns.length === 0 ? (
              <p className="p-8 text-center text-xs text-[var(--text-muted)] font-medium">No evaluation runs found. Click "Trigger Benchmark" to start.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[var(--bg-tertiary)] border-b border-[var(--border-default)] text-[11px] font-bold text-[var(--text-secondary)] uppercase tracking-wider">
                      <th className="p-3">Run Name / ID</th>
                      <th className="p-3">Dataset ID</th>
                      <th className="p-3">Profile</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Samples</th>
                      <th className="p-3">Avg Latency</th>
                      <th className="p-3">Total Cost</th>
                      <th className="p-3">Created</th>
                      <th className="p-3">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalRuns.map((run: EvaluationRun) => (
                      <tr key={run.id} className="border-b border-[var(--border-default)] hover:bg-[var(--bg-tertiary)]/30 text-xs transition-colors">
                        <td className="p-3">
                          <div className="font-semibold text-[var(--text-primary)]">{run.name}</div>
                          <div className="text-[10px] text-[var(--text-muted)] font-mono mt-0.5">{run.id}</div>
                        </td>
                        <td className="p-3">
                          <span className="font-mono text-[var(--text-secondary)]">{run.dataset_id}</span>
                          <span className="text-[10px] text-[var(--text-muted)] ml-1">v{run.dataset_version}</span>
                        </td>
                        <td className="p-3 capitalize">{run.profile}</td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              run.status === "COMPLETED"
                                ? "bg-green-500/10 text-green-400"
                                : run.status === "RUNNING"
                                ? "bg-blue-500/10 text-blue-400 animate-pulse"
                                : "bg-red-500/10 text-red-400"
                            }`}
                          >
                            {run.status}
                          </span>
                        </td>
                        <td className="p-3 font-mono">
                          {run.completed_samples} / {run.total_samples}
                        </td>
                        <td className="p-3 font-mono">{run.avg_latency ? `${run.avg_latency.toFixed(2)}s` : "0.00s"}</td>
                        <td className="p-3 font-mono">${run.total_cost.toFixed(5)}</td>
                        <td className="p-3 text-[var(--text-muted)]">{formatDate(run.created_at)}</td>
                        <td className="p-3">
                          {run.status === "COMPLETED" && (
                            <Button
                              variant="outline"
                              size="xs"
                              onClick={() => setSelectedReportRunId(run.id)}
                              className="gap-1 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/10 text-[11px] font-semibold py-1 h-auto"
                            >
                              <FileText size={11} />
                              <span>View Report</span>
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal A: Start Benchmark Run */}
      {isRunModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] w-full max-w-md overflow-hidden shadow-xl animate-in fade-in-50 zoom-in-95 duration-150">
            <div className="p-5 border-b border-[var(--border-default)]">
              <h3 className="text-sm font-bold font-title">Start Pipeline Benchmark Suite</h3>
              <p className="text-[11px] text-[var(--text-muted)] mt-1">Configure parameters to run RAG evaluation pipelines.</p>
            </div>

            <form onSubmit={handleStartBenchmark}>
              <div className="p-5 space-y-4 text-xs font-semibold">
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Dataset File Path</label>
                  <input
                    type="text"
                    required
                    value={datasetPath}
                    onChange={(e) => setDatasetPath(e.target.value)}
                    className="w-full h-9 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-md px-3 outline-none focus:border-[var(--accent-primary)]/50 focus:ring-1 focus:ring-[var(--accent-primary)]/20 font-mono text-[11px]"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Dataset Identifier</label>
                    <input
                      type="text"
                      required
                      value={datasetId}
                      onChange={(e) => setDatasetId(e.target.value)}
                      className="w-full h-9 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-md px-3 outline-none focus:border-[var(--accent-primary)]/50 focus:ring-1"
                    />
                  </div>
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Dataset Version</label>
                    <input
                      type="text"
                      required
                      value={datasetVersion}
                      onChange={(e) => setDatasetVersion(e.target.value)}
                      className="w-full h-9 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-md px-3 outline-none focus:border-[var(--accent-primary)]/50 focus:ring-1"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Eval Profile</label>
                    <select
                      value={profile}
                      onChange={(e) => setProfile(e.target.value)}
                      className="w-full h-9 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-md px-2 outline-none focus:border-[var(--accent-primary)]/50 focus:ring-1"
                    >
                      <option value="quick">Quick (max 5 samples)</option>
                      <option value="standard">Standard (max 50 samples)</option>
                      <option value="full">Full (max 200 samples)</option>
                      <option value="nightly">Nightly (max 1000 samples)</option>
                    </select>
                  </div>
                  <div className="flex items-center pt-5">
                    <label className="flex items-center gap-2 cursor-pointer text-[var(--text-primary)]">
                      <input
                        type="checkbox"
                        checked={mockMode}
                        onChange={(e) => setMockMode(e.target.checked)}
                        className="rounded border-[var(--border-default)] bg-[var(--bg-input)] text-[var(--accent-primary)] focus:ring-0 cursor-pointer"
                      />
                      <span>Mock Evaluation Mode</span>
                    </label>
                  </div>
                </div>
              </div>

              <div className="p-4 bg-[var(--bg-tertiary)] border-t border-[var(--border-default)] flex justify-end gap-2.5">
                <Button
                  variant="outline"
                  size="sm"
                  type="button"
                  onClick={() => setIsRunModalOpen(false)}
                  className="h-9"
                >
                  Cancel
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  type="submit"
                  disabled={runMutation.isPending}
                  className="h-9 gap-1.5"
                >
                  {runMutation.isPending && (
                    <div className="animate-spin h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full" />
                  )}
                  <span>Launch Benchmark</span>
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal B: Compare Regression Check */}
      {isCompareModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] w-full max-w-lg overflow-hidden shadow-xl animate-in fade-in-50 zoom-in-95 duration-150">
            <div className="p-5 border-b border-[var(--border-default)] flex justify-between items-center">
              <div>
                <h3 className="text-sm font-bold font-title">Compare Runs (Regression Check)</h3>
                <p className="text-[11px] text-[var(--text-muted)] mt-1">Select candidate and baseline evaluation runs to perform delta comparisons.</p>
              </div>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => {
                  setRegressionResult(null);
                  setIsCompareModalOpen(false);
                }}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                Close
              </Button>
            </div>

            <form onSubmit={handleCompareRegression}>
              <div className="p-5 space-y-4 text-xs font-semibold">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Candidate Run ID</label>
                    <select
                      value={candidateRunId}
                      required
                      onChange={(e) => setCandidateRunId(e.target.value)}
                      className="w-full h-9 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-md px-2 outline-none"
                    >
                      <option value="">-- Select Candidate --</option>
                      {evalRuns
                        .filter((r) => r.status === "COMPLETED")
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name.substring(0, 24)}... ({r.id.substring(0, 6)})
                          </option>
                        ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Baseline Run ID</label>
                    <select
                      value={baselineRunId}
                      required
                      onChange={(e) => setBaselineRunId(e.target.value)}
                      className="w-full h-9 bg-[var(--bg-input)] border border-[var(--border-default)] hover:border-[var(--border-hover)] rounded-md px-2 outline-none"
                    >
                      <option value="">-- Select Baseline --</option>
                      {evalRuns
                        .filter((r) => r.status === "COMPLETED" && r.id !== candidateRunId)
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name.substring(0, 24)}... ({r.id.substring(0, 6)})
                          </option>
                        ))}
                    </select>
                  </div>
                </div>

                {regressionResult && (
                  <div className="bg-[var(--bg-input)] border border-[var(--border-subtle)] rounded-md p-4 space-y-3">
                    <div className="flex justify-between items-center pb-2 border-b border-[var(--border-subtle)]">
                      <span className="font-bold">Regression Check Status</span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          regressionResult.passed
                            ? "bg-green-500/10 text-green-400"
                            : "bg-red-500/10 text-red-400"
                        }`}
                      >
                        {regressionResult.passed ? "🟢 PASSED" : "🔴 FAILED"}
                      </span>
                    </div>

                    <div className="max-h-40 overflow-y-auto space-y-1.5 font-mono text-[11px]">
                      {Object.entries(regressionResult.metric_deltas).map(([metric, val]) => {
                        const isPos = val > 0.01;
                        const isNeg = val < -0.01;
                        return (
                          <div key={metric} className="flex justify-between items-center py-0.5">
                            <span>{metric}</span>
                            <span className={isPos ? "text-green-400" : isNeg ? "text-red-400 font-bold" : "text-[var(--text-muted)]"}>
                              {val >= 0 ? `+${val.toFixed(3)}` : val.toFixed(3)} {isPos ? "▲" : isNeg ? "▼" : "—"}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              <div className="p-4 bg-[var(--bg-tertiary)] border-t border-[var(--border-default)] flex justify-end gap-2.5">
                <Button
                  variant="outline"
                  size="sm"
                  type="button"
                  onClick={() => {
                    setRegressionResult(null);
                    setIsCompareModalOpen(false);
                  }}
                  className="h-9"
                >
                  Cancel
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  type="submit"
                  disabled={compareMutation.isPending}
                  className="h-9 gap-1.5"
                >
                  {compareMutation.isPending && (
                    <div className="animate-spin h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full" />
                  )}
                  <span>Compare Runs</span>
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal C: View styled HTML Report */}
      {selectedReportRunId && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded-[var(--radius-lg)] w-full max-w-4xl overflow-hidden shadow-xl animate-in fade-in-50 zoom-in-95 duration-150">
            <div className="p-4 border-b border-[var(--border-default)] flex justify-between items-center">
              <div>
                <h3 className="text-sm font-bold font-title">Benchmark HTML Performance Report</h3>
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Run: {selectedReportRunId}</p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSelectedReportRunId(null);
                  setReportHtml("");
                }}
                className="h-9"
              >
                Close Report
              </Button>
            </div>

            <div className="bg-[#f3f4f6] p-2 h-[75vh] flex items-center justify-center relative">
              {isLoadingReport ? (
                <div className="flex flex-col items-center gap-2">
                  <div className="animate-spin h-6 w-6 border-2 border-[var(--accent-primary)] border-t-transparent rounded-full" />
                  <p className="text-xs text-[var(--text-muted)] font-medium">Fetching report from server...</p>
                </div>
              ) : (
                <iframe
                  srcDoc={reportHtml}
                  title="Benchmark HTML Report"
                  className="w-full h-full border-0 bg-white rounded-md shadow-sm"
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDashboardPage;
