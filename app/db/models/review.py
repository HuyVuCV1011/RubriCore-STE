import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class ReviewTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id"))
    assessment_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessment_items.id"))
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    grading_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grading_runs.id"))
    grading_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grading_results.id"))
    assigned_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(40), nullable=False, default="normal")
    confidence_band: Mapped[str | None] = mapped_column(String(40))
    escalation_reason: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "status in ('open', 'assigned', 'completed', 'cancelled')",
            name="review_task_status",
        ),
        CheckConstraint(
            "priority in ('low', 'normal', 'high', 'urgent')",
            name="review_task_priority",
        ),
        Index("ix_review_tasks_organization_status", "organization_id", "status"),
        Index("ix_review_tasks_status_reviewer", "status", "assigned_reviewer_id"),
        Index("ix_review_tasks_assessment", "assessment_id"),
        Index("ix_review_tasks_confidence_band", "confidence_band"),
        Index("ix_review_tasks_escalation_reason", "escalation_reason"),
        Index("ix_review_tasks_created_at", "created_at"),
    )


class TeacherReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teacher_reviews"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    review_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_tasks.id"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    grading_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grading_results.id"))
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    final_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "decision in ('approve', 'adjust', 'override', 'return_for_regrade')",
            name="teacher_review_decision",
        ),
        Index("ix_teacher_reviews_organization", "organization_id"),
        Index("ix_teacher_reviews_review_task", "review_task_id"),
        Index("ix_teacher_reviews_reviewer", "reviewer_id"),
    )


class TeacherOverride(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teacher_overrides"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    teacher_review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teacher_reviews.id"), nullable=False)
    grading_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("grading_results.id"), nullable=False)
    overridden_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    override_type: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    new_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "override_type in ('score', 'feedback', 'criterion_result', 'finalization')",
            name="teacher_override_type",
        ),
        Index("ix_teacher_overrides_organization", "organization_id"),
        Index("ix_teacher_overrides_grading_result", "grading_result_id"),
    )
