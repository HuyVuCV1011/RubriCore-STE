import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class GradingRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grading_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    rubric_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rubric_versions.id"))
    answer_key_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("answer_key_versions.id"))
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    trigger_source: Mapped[str] = mapped_column(String(80), nullable=False, default="system")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    grading_policy_version: Mapped[str | None] = mapped_column(String(80))
    context_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    results: Mapped[list["GradingResult"]] = relationship(back_populates="grading_run")

    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="grading_run_status",
        ),
        Index("ix_grading_runs_organization_status", "organization_id", "status"),
        Index("ix_grading_runs_submission_status", "submission_id", "status"),
        Index("ix_grading_runs_rubric_version", "rubric_version_id"),
        Index("ix_grading_runs_answer_key_version", "answer_key_version_id"),
    )


class GradingResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grading_results"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    grading_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grading_runs.id"), nullable=False)
    rubric_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rubric_versions.id"))
    answer_key_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("answer_key_versions.id"))
    result_type: Mapped[str] = mapped_column(String(40), nullable=False, default="proposed")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="proposed")
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    max_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    feedback: Mapped[str | None] = mapped_column(Text)
    explanation_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    grading_run: Mapped[GradingRun] = relationship(back_populates="results")
    criterion_results: Mapped[list["CriterionResult"]] = relationship(back_populates="grading_result")

    __table_args__ = (
        CheckConstraint(
            "result_type in ('proposed', 'final', 'reviewed', 'overridden')",
            name="grading_result_type",
        ),
        CheckConstraint(
            "status in ('proposed', 'needs_review', 'finalized', 'superseded')",
            name="grading_result_status",
        ),
        CheckConstraint(
            "confidence is null or (confidence >= 0 and confidence <= 1)",
            name="grading_result_confidence_range",
        ),
        Index("ix_grading_results_organization_status", "organization_id", "status"),
        Index("ix_grading_results_grading_run", "grading_run_id"),
        Index("ix_grading_results_rubric_version", "rubric_version_id"),
        Index("ix_grading_results_answer_key_version", "answer_key_version_id"),
    )


class CriterionResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "criterion_results"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    grading_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("grading_results.id"),
        nullable=False,
    )
    criterion_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    max_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    explanation: Mapped[str | None] = mapped_column(Text)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    grading_result: Mapped[GradingResult] = relationship(back_populates="criterion_results")

    __table_args__ = (
        CheckConstraint(
            "source in ('deterministic', 'ai', 'teacher', 'system')",
            name="criterion_result_source",
        ),
        CheckConstraint(
            "confidence is null or (confidence >= 0 and confidence <= 1)",
            name="criterion_result_confidence_range",
        ),
        Index("ix_criterion_results_grading_result", "grading_result_id"),
    )


class AIInteraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_interactions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    grading_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grading_runs.id"))
    grading_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grading_results.id"))
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    output_schema_version: Mapped[str | None] = mapped_column(String(80))
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    request_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    provider_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "validation_status in ('pending', 'valid', 'invalid', 'failed')",
            name="ai_interaction_validation_status",
        ),
        Index("ix_ai_interactions_organization", "organization_id"),
        Index("ix_ai_interactions_grading_run", "grading_run_id"),
        Index("ix_ai_interactions_validation_status", "validation_status"),
    )
