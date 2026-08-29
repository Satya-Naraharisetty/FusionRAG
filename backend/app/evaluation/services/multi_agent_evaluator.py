import logging
import math

from app.evaluation.domain.models import (
    EvaluationResult,
    EvaluationSample,
    MetricResult,
    MultiAgentEvaluation,
)

logger = logging.getLogger(__name__)


class MultiAgentEvaluator:
    """
    Evaluator for multi-agent architecture measuring observable behaviors:
    1. Planning Accuracy: correct specialists and dependency ordering.
    2. Routing Accuracy: matching task capabilities without budget/policy rejections.
    3. Dependency Execution Success: successful data propagation across DAG.
    4. Bounded Replanning: bounded refinement on incomplete/failed outcomes.
    5. Calculation Accuracy: deterministic math verification.
    6. Synthesis Grounding: evidence-backed citation attribution.
    """

    async def evaluate_samples(
        self, samples: list[EvaluationSample], mock: bool = False
    ) -> list[EvaluationResult]:
        results: list[EvaluationResult] = []

        for sample in samples:
            meta = sample.metadata or {}
            actual_plan = meta.get("actual_plan", {})
            actual_tasks = meta.get("actual_tasks", [])
            actual_diagnostics = meta.get("agent_diagnostics", {})
            actual_output = meta.get("actual_output") or meta.get("actual_answer", "")
            citations = meta.get("citations", [])

            # 1. Planning Accuracy
            expected_specialists = meta.get("expected_specialists")
            planned_specialists = [
                t.get("agent_type") for t in actual_tasks if t.get("agent_type")
            ]
            if not planned_specialists and actual_plan.get("tasks"):
                planned_specialists = [
                    t.get("agent_type") for t in actual_plan["tasks"]
                ]

            if expected_specialists:
                matched_specs = sum(
                    1 for s in expected_specialists if s in planned_specialists
                )
                plan_score = (
                    matched_specs / len(expected_specialists)
                    if expected_specialists
                    else 1.0
                )
            else:
                plan_score = 1.0

            # 2. Routing Accuracy
            expected_routes = meta.get("expected_routes", {})
            routed_correctly = 0
            total_routing_checks = len(expected_routes) if expected_routes else 0
            if total_routing_checks > 0:
                for task in actual_tasks:
                    t_id = task.get("task_id")
                    r_cap = task.get("routed_capability")
                    if t_id in expected_routes and r_cap == expected_routes[t_id]:
                        routed_correctly += 1
                routing_score = (
                    routed_correctly / total_routing_checks
                    if total_routing_checks
                    else 1.0
                )
            else:
                routing_score = (
                    1.0 if not actual_diagnostics.get("failed_tasks") else 0.8
                )

            # 3. Dependency Execution Success
            dep_tasks = [t for t in actual_tasks if t.get("dependencies")]
            if dep_tasks:
                successful_dep_tasks = sum(
                    1 for t in dep_tasks if t.get("success", False)
                )
                dep_score = successful_dep_tasks / len(dep_tasks)
            else:
                dep_score = 1.0

            # 4. Replanning Behavior
            trigger_replan = meta.get("trigger_replan", False)
            actual_replans = actual_diagnostics.get("plan_iterations", 1) - 1
            if actual_replans < 0:
                actual_replans = 0

            if trigger_replan:
                # Should have triggered at least 1 replan but stayed within bounded limit (<= 2)
                replan_score = 1.0 if 1 <= actual_replans <= 2 else 0.0
            else:
                # Should not have triggered unnecessary replans
                replan_score = 1.0 if actual_replans == 0 else 0.5

            # 5. Calculation Accuracy
            expected_numeric = meta.get("expected_numeric_output")
            actual_numeric = meta.get("actual_numeric_output")
            calc_score = 1.0
            if expected_numeric is not None:
                if actual_numeric is not None:
                    calc_score = (
                        1.0
                        if math.isclose(
                            float(actual_numeric),
                            float(expected_numeric),
                            rel_tol=1e-3,
                            abs_tol=1e-3,
                        )
                        else 0.0
                    )
                else:
                    calc_score = 0.0

            # 6. Synthesis Grounding
            evidence_count = actual_diagnostics.get("evidence_count", 0)
            citation_count = len(citations)
            if sample.retrieval_required and evidence_count > 0:
                grounding_score = 1.0 if citation_count > 0 else 0.5
            else:
                grounding_score = 1.0

            # Aggregate Metric Results
            metrics = [
                MetricResult(
                    name="multi_agent_planning_accuracy",
                    score=plan_score,
                    passed=plan_score >= 0.8,
                    reason=f"Planned specialists {planned_specialists} vs expected {expected_specialists}",
                ),
                MetricResult(
                    name="multi_agent_routing_accuracy",
                    score=routing_score,
                    passed=routing_score >= 0.8,
                    reason="All tasks assigned to authorized capabilities without policy rejection",
                ),
                MetricResult(
                    name="multi_agent_dependency_execution",
                    score=dep_score,
                    passed=dep_score >= 0.8,
                    reason=f"Dependency execution score: {dep_score:.2f}",
                ),
                MetricResult(
                    name="multi_agent_replanning_success",
                    score=replan_score,
                    passed=replan_score >= 0.8,
                    reason=f"Replanning iterations: {actual_replans}, expected replan: {trigger_replan}",
                ),
                MetricResult(
                    name="multi_agent_calculation_accuracy",
                    score=calc_score,
                    passed=calc_score >= 0.99,
                    reason=f"Actual numeric: {actual_numeric} vs expected: {expected_numeric}",
                ),
                MetricResult(
                    name="multi_agent_synthesis_grounding",
                    score=grounding_score,
                    passed=grounding_score >= 0.8,
                    reason=f"Citations returned: {citation_count} for evidence items: {evidence_count}",
                ),
            ]

            all_passed = all(m.passed for m in metrics if m.passed is not None)
            eval_details = MultiAgentEvaluation(
                planning_accuracy=plan_score,
                routing_accuracy=routing_score,
                dependency_execution_success=dep_score,
                replanning_success_rate=replan_score,
                calculation_accuracy=calc_score,
                synthesis_grounding=grounding_score,
                total_specialist_calls=actual_diagnostics.get(
                    "total_specialist_calls", len(actual_tasks)
                ),
                concurrency_savings_ms=actual_diagnostics.get(
                    "concurrency_savings_ms", 0.0
                ),
                passed=all_passed,
            )

            sample_metadata = dict(meta)
            sample_metadata["multi_agent_evaluation"] = eval_details.model_dump()

            results.append(
                EvaluationResult(
                    sample_id=sample.id,
                    question=sample.question,
                    expected_answer=sample.expected_answer,
                    actual_answer=str(actual_output),
                    latency=float(actual_diagnostics.get("total_time_ms", 0.0)),
                    error_category="None" if all_passed else "MultiAgent Failure",
                    metrics=metrics,
                    metadata=sample_metadata,
                )
            )

        return results
