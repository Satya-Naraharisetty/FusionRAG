import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_context, get_db
from app.chat.infrastructure.persistence.models import ConversationMessageORM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observability", tags=["Observability"])


def check_admin_user(
    user_context: dict[str, Any] = Depends(get_current_user_context),
) -> dict[str, Any]:
    """
    Dependency to restrict observability endpoints to admin users.
    """
    if user_context.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permissions required to access observability logs.",
        )
    return user_context


# Models for response validation
class TraceItem(BaseModel):
    id: UUID
    conversation_id: UUID
    question: str
    answer: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    retrieval_time_ms: float | None = None
    generation_time_ms: float | None = None
    total_time_ms: float | None = None
    created_at: datetime
    citations_count: int


class DailyMetric(BaseModel):
    date: str
    tokens: int
    cost: float
    avg_latency_ms: float


class ObservabilityMetricsResponse(BaseModel):
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost: float
    avg_total_latency_ms: float
    avg_retrieval_latency_ms: float
    avg_generation_latency_ms: float
    daily_usage: list[DailyMetric]


class TraceListResponse(BaseModel):
    total: int
    items: list[TraceItem]


def calculate_estimated_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """
    Utility to compute generic estimated cost for LLM calls based on token count.
    Estimates based on typical Gemini 1.5 Flash rates:
    - Input: $0.075 per 1,000,000 tokens ($0.000000075 per token)
    - Output: $0.30 per 1,000,000 tokens ($0.0000003 per token)
    """
    return (prompt_tokens * 0.000000075) + (completion_tokens * 0.0000003)


@router.get(
    "/metrics",
    response_model=ObservabilityMetricsResponse,
    dependencies=[Depends(check_admin_user)],
)
def get_observability_metrics(db: Session = Depends(get_db)) -> Any:
    """
    Fetch aggregated observability metrics over the last 30 days.
    """
    # Fetch completed assistant messages
    messages = (
        db.query(ConversationMessageORM)
        .filter(
            ConversationMessageORM.role == "assistant",
            ConversationMessageORM.status == "completed",
        )
        .all()
    )

    total_prompt = 0
    total_completion = 0
    retrieval_latencies = []
    generation_latencies = []
    total_latencies = []

    # Map daily stats (date string -> lists of values)
    daily_data: dict[str, dict[str, Any]] = {}

    # Initialize last 7 days keys
    today = datetime.utcnow().date()
    for i in range(7):
        d_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_data[d_str] = {
            "tokens": 0,
            "cost": 0.0,
            "latencies": [],
        }

    for msg in messages:
        p_t = msg.prompt_tokens or 0
        c_t = msg.completion_tokens or 0
        cost = calculate_estimated_cost(p_t, c_t)

        total_prompt += p_t
        total_completion += c_t

        meta = msg.metadata_json or {}
        r_ms = meta.get("retrieval_time_ms")
        g_ms = meta.get("generation_time_ms")
        t_ms = meta.get("total_time_ms")

        if r_ms is not None:
            retrieval_latencies.append(float(r_ms))
        if g_ms is not None:
            generation_latencies.append(float(g_ms))
        if t_ms is not None:
            total_latencies.append(float(t_ms))

        # Add to daily metrics if it falls in the last 7 days
        msg_date = msg.created_at.date()
        date_str = msg_date.strftime("%Y-%m-%d")
        if date_str in daily_data:
            daily_data[date_str]["tokens"] += p_t + c_t
            daily_data[date_str]["cost"] += cost
            if t_ms is not None:
                daily_data[date_str]["latencies"].append(float(t_ms))

    avg_retrieval = (
        sum(retrieval_latencies) / len(retrieval_latencies)
        if retrieval_latencies
        else 0.0
    )
    avg_generation = (
        sum(generation_latencies) / len(generation_latencies)
        if generation_latencies
        else 0.0
    )
    avg_total = sum(total_latencies) / len(total_latencies) if total_latencies else 0.0
    total_cost = calculate_estimated_cost(total_prompt, total_completion)

    # Format daily stats (sorted chronologically)
    formatted_daily = []
    for k in sorted(daily_data.keys()):
        day_vals = daily_data[k]
        lats = day_vals["latencies"]
        avg_lat = sum(lats) / len(lats) if lats else 0.0
        formatted_daily.append(
            DailyMetric(
                date=k,
                tokens=day_vals["tokens"],
                cost=round(day_vals["cost"], 5),
                avg_latency_ms=round(avg_lat, 2),
            )
        )

    return ObservabilityMetricsResponse(
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_prompt + total_completion,
        total_cost=round(total_cost, 4),
        avg_total_latency_ms=round(avg_total, 2),
        avg_retrieval_latency_ms=round(avg_retrieval, 2),
        avg_generation_latency_ms=round(avg_generation, 2),
        daily_usage=formatted_daily,
    )


@router.get(
    "/traces",
    response_model=TraceListResponse,
    dependencies=[Depends(check_admin_user)],
)
def get_observability_traces(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Any:
    """
    Fetch paginated traces of recent completed assistant messages.
    """
    query = db.query(ConversationMessageORM).filter(
        ConversationMessageORM.role == "assistant",
        ConversationMessageORM.status == "completed",
    )

    total = query.count()

    messages = (
        query.order_by(ConversationMessageORM.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    trace_items = []
    for msg in messages:
        # Find preceding user message for this conversation
        user_msg = (
            db.query(ConversationMessageORM)
            .filter(
                ConversationMessageORM.conversation_id == msg.conversation_id,
                ConversationMessageORM.role == "user",
                ConversationMessageORM.created_at < msg.created_at,
            )
            .order_by(ConversationMessageORM.created_at.desc())
            .first()
        )

        question = user_msg.content if user_msg else "N/A"
        prompt_t = msg.prompt_tokens or 0
        comp_t = msg.completion_tokens or 0
        total_t = prompt_t + comp_t
        cost = calculate_estimated_cost(prompt_t, comp_t)

        meta = msg.metadata_json or {}
        r_ms = meta.get("retrieval_time_ms")
        g_ms = meta.get("generation_time_ms")
        t_ms = meta.get("total_time_ms")

        citations_count = len(msg.citations) if msg.citations else 0

        trace_items.append(
            TraceItem(
                id=msg.id,
                conversation_id=msg.conversation_id,
                question=question,
                answer=msg.content,
                prompt_tokens=prompt_t,
                completion_tokens=comp_t,
                total_tokens=total_t,
                cost=round(cost, 5),
                retrieval_time_ms=float(r_ms) if r_ms is not None else None,
                generation_time_ms=float(g_ms) if g_ms is not None else None,
                total_time_ms=float(t_ms) if t_ms is not None else None,
                created_at=msg.created_at,
                citations_count=citations_count,
            )
        )

    return TraceListResponse(total=total, items=trace_items)
