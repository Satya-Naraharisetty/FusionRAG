import uuid
from datetime import datetime, UTC
from typing import Any
from pydantic import BaseModel, Field


class RetrievedContext(BaseModel):
    text: str
    score: float | None = None
    chunk_id: str | None = None
    document_id: str | None = None


class EvaluationSample(BaseModel):
    id: str
    question: str
    expected_answer: str | None = None
    ground_truth_context: list[str] | None = None
    conversation_history: list[dict[str, Any]] | None = None
    expected_tools: list[str] | None = None
    expected_citations: list[str] | None = None
    difficulty: str | None = "medium"  # easy, medium, hard
    topic: str | None = None
    retrieval_required: bool = True
    tools_required: bool = False
    conversation_required: bool = False
    expected_documents: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationDataset(BaseModel):
    dataset_id: str
    version: str
    hash: str
    sample_count: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    description: str | None = None
    samples: list[EvaluationSample] = Field(default_factory=list)


class MetricResult(BaseModel):
    name: str
    score: float
    passed: bool | None = None
    reason: str | None = None


class EvaluationResult(BaseModel):
    sample_id: str
    question: str
    expected_answer: str | None = None
    actual_answer: str | None = None
    latency: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    error_category: str = "None"  # Retrieval Failure, Hallucination, etc.
    metrics: list[MetricResult] = Field(default_factory=list)
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkRun(BaseModel):
    id: uuid.UUID
    name: str
    profile: str
    status: str
    results_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RegressionRun(BaseModel):
    baseline_run_id: uuid.UUID
    candidate_run_id: uuid.UUID
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ConversationEvaluation(BaseModel):
    history_rewrite_score: float = 0.0
    memory_retention_score: float = 0.0
    summary_quality_score: float = 0.0
    context_budget_utilization: float = 0.0
    passed: bool = True
    reason: str | None = None


class AgentEvaluation(BaseModel):
    reasoning_steps: int = 0
    reasoning_efficiency: float = 0.0  # e.g., steps vs correct output ratio
    tool_necessity_score: float = 1.0
    tool_ordering_correctness: float = 1.0
    iteration_count: int = 0
    passed: bool = True
    reason: str | None = None


class ToolEvaluation(BaseModel):
    tool_success_rate: float = 1.0
    validation_failures: int = 0
    timeouts: int = 0
    retries: int = 0
    latency: float = 0.0
    correct_tool_chosen: bool = True
    passed: bool = True
    reason: str | None = None
