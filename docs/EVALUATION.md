# Hybrid RAG Evaluation & Regression Framework

## 1. Operational Confidence Levels

The Hybrid RAG evaluation subsystem avoids equating offline benchmark scores with production readiness by enforcing a rigorous five-category operational confidence model:

| Category | Status | Definition & Repository Evidence |
|---|---|---|
| **Benchmark-Proven** | ✅ Validated | Evaluated over versioned golden datasets (`golden_rag_dataset`, `golden_multi_agent_v1`) under deterministic/mocked test execution. Verifies evaluator mechanics, DAG routing, and deterministic invariants. |
| **Repository-Proven** | ✅ Validated with 1 known failure | Verified via automated integration and unit test suites with hermetic mocking. **663 tests passed, 1 known test failed** due to an environment-specific Upstash Redis Windows SSL socket shutdown timing issue (`test_shutdown_job_finishes_within_grace_period`). |
| **Production-Observable** | ✅ Instrumented | Fully instrumented with low-cardinality Prometheus collectors (`AGENT_LLM_TOKENS`, `AGENT_LLM_DURATION`, `AGENT_REPLANS`, `AGENT_TASKS_EXECUTED`), OpenTelemetry distributed traces, and sanitized structured JSON logs. |
| **Live-Production Observed** | ❌ Not yet demonstrated | Requires observation under real-world multi-tenant traffic (live Gemini API calls, real SSE streaming backpressure, actual token distributions, real-world cache hit ratios). |
| **Load / Adversarially Verified** | ❌ Not yet demonstrated | High-concurrency saturation (p95/p99 latency under load), thread-pool contention, and extensive live adversarial prompt injection suites remain to be proven in staging/production. |

---

## 2. Multi-Agent Evaluation Dimensions (10 Dimensions)

The `MultiAgentEvaluator` evaluates observable pipeline outputs across 10 distinct quality and safety criteria:

| # | Evaluation Dimension | Metric Name | Pass Threshold | Description |
|---|---|---|---|---|
| 1 | **Planning Accuracy** | `multi_agent_planning_accuracy` | $\ge 0.80$ | Validates that required specialist agents (Research, Analysis, Web Search, Document) are planned in valid DAG order. |
| 2 | **Routing Accuracy** | `multi_agent_routing_accuracy` | $\ge 0.80$ | Validates capability matching, authorization policies, and budget allocations. |
| 3 | **Dependency Execution** | `multi_agent_dependency_execution` | $\ge 0.80$ | Verifies data propagation across dependent DAG tasks. |
| 4 | **Bounded Replanning** | `multi_agent_replanning_success` | $\ge 0.80$ | Confirms that queries with insufficient initial evidence trigger bounded replanning ($\le 2$ iterations). |
| 5 | **Calculation Accuracy** | `multi_agent_calculation_accuracy` | $\ge 0.99$ | Deterministic AST-sandboxed math verification without numeric hallucination. |
| 6 | **Synthesis Grounding** | `multi_agent_synthesis_grounding` | $\ge 0.80$ | Ensures answers are strictly attributed to retrieved and cited evidence chunks. |
| 7 | **Refusal Faithfulness** | `multi_agent_refusal_faithfulness` | $\ge 0.90$ | Verifies explicit acknowledgment of absent knowledge/evidence without hallucinating answers. |
| 8 | **Contradiction Detection & Synthesis** | `multi_agent_contradiction_detection` | $\ge 0.80$ | Requires identifying conflicting claims, citing both contradictory sources, and avoiding arbitrary one-sided bias. |
| 9 | **Indirect Injection Resistance** | `multi_agent_injection_resistance` | $\ge 0.99$ | Confirms model treats retrieved document text strictly as untrusted data rather than executable instructions. |
| 10 | **Replanning Exhaustion Handling** | `multi_agent_replanning_exhaustion` | $\ge 0.80$ | Ensures execution halts gracefully at the iteration bound with a structured diagnostic notice when dependencies repeatedly fail. |

> [!NOTE]
> 10/10 deterministic evaluation cases passed under mocked execution. This validates the evaluator, dataset wiring, expected control flow, and deterministic invariants; it does not constitute evidence of live LLM behavioral accuracy.

---

## 3. Dual-Gate Regression Governance

The regression runner (`backend/scripts/regression.py`) enforces dual-gate governance to ensure candidates do not regress:

1. **Gate 1 — Absolute Minimum Quality Floor**:
   $$\text{candidate\_metric} \ge \text{minimum\_quality\_floor}$$
   A candidate immediately fails if any metric breaches its safety floor (e.g. calculation $< 0.99$, injection resistance $< 0.99$, hit rate $< 0.90$).
2. **Gate 2 — Maximum Allowed Degradation from Baseline**:
   $$\text{candidate\_metric} \ge \text{baseline\_metric} - \text{max\_score\_drop}$$
   A candidate fails if any metric drops by more than `max_score_drop` (default 0.03 = 3%) from the approved baseline artifact (`baseline_multi_agent_v1.json`, `baseline_v1.json`).
3. **Latency Regression Guard**: Rejects candidates exceeding a 20% latency increase when baseline latency exceeds 10ms.

### Negative Regression Tests (Proven Failure Gates)

The regression harness has been explicitly verified against negative test cases:
* **Quality Floor Breach**: Candidate calculation accuracy of 0.92 is rejected against the 0.99 floor (`[FAIL] BELOW_QUALITY_FLOOR`).
* **Score Drop Regression**: Candidate dropping from 1.00 to 0.92 is rejected against the 0.03 maximum drop threshold (`[FAIL] REGRESSION`).
* **Latency Degradation**: Latency increase of +100% is rejected against the 20% threshold (`[FAIL] REGRESSION`).
* **Dataset/Profile Mismatch**: Mismatched versions or profiles raise compatibility errors (`ValueError`).

### CLI Usage

```bash
# Run multi-agent benchmark
uv run python scripts/benchmark.py \
  --dataset app/evaluation/datasets/golden/golden_multi_agent.yaml \
  --profile multi_agent \
  --mock

# Run regression check against approved baseline
uv run python scripts/regression.py \
  --baseline-file app/evaluation/baselines/baseline_multi_agent_v1.json \
  --candidate-json data/evaluation/report_<RUN_ID>.json
```

---

## 4. Telemetry & Cardinality Rules

To prevent cardinality explosions in Prometheus:
- **Forbidden Prometheus Labels**: `user_id`, `conversation_id`, `request_id`, `task_id`, `document_id`, `chunk_id`.
- **Allowed Prometheus Labels**: Static, low-cardinality enums (`provider`, `model`, `agent_role`, `specialist_type`, `operation`, `status`, `reason`).
- **High-Cardinality Identifiers**: Retained exclusively in structured JSON logs (`AgentTraceEvent`) and OpenTelemetry trace spans.
