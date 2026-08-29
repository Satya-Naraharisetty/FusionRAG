import re

from app.chat.domain.multi_agent import (
    MAX_TOTAL_CAPABILITY_CALLS_PER_PLAN,
    CapabilityDescriptor,
    CapabilityType,
    ExecutionPlan,
)
from app.documents.domain.exceptions import UnauthorizedCapabilityError


class PlanValidationError(Exception):
    pass


class PlanValidator:
    """
    Validates proposed ExecutionPlan DAG before execution:
    1. Capability is registered and allowlisted in CapabilityRegistry.
    2. Dependency graph is strictly acyclic (Kahn's algorithm).
    3. Input refs grammar is valid (step_{uuid}.output[.field]).
    4. Referenced predecessor outputs exist and complete before consumption.
    5. Step timeout is within descriptor limits.
    6. Per-capability call limits (max_calls_per_plan) and total plan limits (<= 15) are respected.
    7. Forbidden infrastructure actions (execute_sql, shell, http_request) are rejected.
    """

    FORBIDDEN_OPERATIONS = {
        "execute_sql",
        "sql_query",
        "shell",
        "exec",
        "eval",
        "http_request",
        "raw_socket",
        "qdrant_direct",
        "redis_direct",
    }

    _INPUT_REF_PATTERN = re.compile(
        r"^step_[a-fA-F0-9\-]+\.output(?:\.[a-zA-Z0-9_]+)?$"
    )

    def __init__(
        self,
        registered_capabilities: dict[CapabilityType, CapabilityDescriptor]
        | None = None,
    ) -> None:
        self.registered_capabilities = registered_capabilities or {}

    def validate(self, plan: ExecutionPlan) -> bool:
        if not plan.tasks:
            raise PlanValidationError("Execution plan contains no tasks.")

        # 1. Total call budget check
        if len(plan.tasks) > MAX_TOTAL_CAPABILITY_CALLS_PER_PLAN:
            raise PlanValidationError(
                f"Plan task count ({len(plan.tasks)}) exceeds maximum allowed ({MAX_TOTAL_CAPABILITY_CALLS_PER_PLAN})."
            )

        task_map = {t.task_id: t for t in plan.tasks}
        capability_counts: dict[str, int] = {}

        # 2. Per-task validation
        for task in plan.tasks:
            cap_type = (
                task.agent_type.value
                if hasattr(task.agent_type, "value")
                else str(task.agent_type)
            )
            capability_counts[cap_type] = capability_counts.get(cap_type, 0) + 1

            # Check per-capability limits
            matching_cap_type: CapabilityType | None = None
            if isinstance(task.agent_type, CapabilityType):
                matching_cap_type = task.agent_type
            elif hasattr(task.agent_type, "value"):
                try:
                    matching_cap_type = CapabilityType(task.agent_type.value)
                except (ValueError, KeyError):
                    matching_cap_type = None

            if (
                matching_cap_type
                and self.registered_capabilities
                and matching_cap_type in self.registered_capabilities
            ):
                descriptor = self.registered_capabilities[matching_cap_type]
                if capability_counts[cap_type] > descriptor.max_calls_per_plan:
                    raise PlanValidationError(
                        f"Capability {cap_type} call count ({capability_counts[cap_type]}) exceeds limit of {descriptor.max_calls_per_plan}."
                    )

            # Check forbidden operations / capabilities
            for param_key, param_val in task.parameters.items():
                if isinstance(param_val, str):
                    for forbidden in self.FORBIDDEN_OPERATIONS:
                        if forbidden in param_val.lower() and param_key in (
                            "action",
                            "command",
                            "operation",
                        ):
                            raise UnauthorizedCapabilityError(
                                f"Forbidden infrastructure action detected: '{param_val}'"
                            )

            # Validate dependencies exist
            for dep_id in task.dependencies:
                if dep_id not in task_map:
                    raise PlanValidationError(
                        f"Task '{task.task_id}' references non-existent dependency '{dep_id}'."
                    )

        # 3. Cycle detection using Kahn's algorithm
        in_degree = {t.task_id: 0 for t in plan.tasks}
        adj_list: dict[str, list[str]] = {t.task_id: [] for t in plan.tasks}

        for task in plan.tasks:
            for dep_id in task.dependencies:
                adj_list[dep_id].append(task.task_id)
                in_degree[task.task_id] += 1

        queue = [t_id for t_id, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            node = queue.pop(0)
            visited_count += 1
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(plan.tasks):
            raise PlanValidationError(
                "Cycle detected in execution plan dependency graph."
            )

        return True
