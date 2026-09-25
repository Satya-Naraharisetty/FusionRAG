import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SQLAlchemyEvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # quick, standard, full, nightly
    dataset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    reranker: Mapped[str] = mapped_column(String(100), nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(100), nullable=False)
    system_prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    git_commit: Mapped[str] = mapped_column(String(100), nullable=True)
    git_branch: Mapped[str] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="RUNNING", nullable=False
    )  # RUNNING, COMPLETED, FAILED
    total_samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_latency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_latency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    results: Mapped[list["SQLAlchemyEvaluationResult"]] = relationship(
        "SQLAlchemyEvaluationResult",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SQLAlchemyEvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    sample_id: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=True)
    actual_answer: Mapped[str] = mapped_column(Text, nullable=True)
    latency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_category: Mapped[str] = mapped_column(
        String(100), default="None", nullable=False
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    retrieved_contexts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped["SQLAlchemyEvaluationRun"] = relationship(
        "SQLAlchemyEvaluationRun", back_populates="results"
    )


class SQLAlchemyBenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False)
    results_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
