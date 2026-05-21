import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id"))
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    grading_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("grading_runs.id"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_source: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    request_id: Mapped[str | None] = mapped_column(String(160))
    job_id: Mapped[str | None] = mapped_column(String(160))
    previous_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    new_state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_audit_events_organization", "organization_id"),
        Index("ix_audit_events_actor", "actor_user_id"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_assessment", "assessment_id"),
        Index("ix_audit_events_submission", "submission_id"),
        Index("ix_audit_events_grading_run", "grading_run_id"),
        Index("ix_audit_events_created_at", "created_at"),
    )
