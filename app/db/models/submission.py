import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.file_artifact import FileArtifact


class Submission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "submissions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id"))
    assessment_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessment_items.id"))
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learners.id"), nullable=False)
    supersedes_submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    superseded_by_submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    evidence: Mapped[list["SubmissionEvidence"]] = relationship(back_populates="submission")

    __table_args__ = (
        CheckConstraint(
            "status in ("
            "'draft', 'submitted', 'superseded', 'withdrawn', 'archived', "
            "'processing', 'graded', 'returned'"
            ")",
            name="submission_status",
        ),
        CheckConstraint(
            "superseded_by_submission_id is null or status = 'superseded'",
            name="submission_superseded_by_requires_status",
        ),
        CheckConstraint(
            "assessment_id is not null or assessment_item_id is not null",
            name="submission_has_assessment_context",
        ),
        Index("ix_submissions_organization_status", "organization_id", "status"),
        Index("ix_submissions_assessment_item_learner", "assessment_item_id", "learner_id"),
        Index("ix_submissions_assessment_learner", "assessment_id", "learner_id"),
        Index("ix_submissions_supersedes", "supersedes_submission_id"),
        Index("ix_submissions_superseded_by", "superseded_by_submission_id"),
    )


class SubmissionEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "submission_evidence"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    evidence_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_types.id"), nullable=False)
    file_artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("file_artifacts.id"))
    evidence_extraction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_extractions.id"))
    raw_text: Mapped[str | None] = mapped_column(Text)
    value_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="submitted")

    submission: Mapped[Submission] = relationship(back_populates="evidence")
    file_artifact: Mapped["FileArtifact | None"] = relationship(foreign_keys=[file_artifact_id])

    __table_args__ = (
        CheckConstraint(
            "status in ('submitted', 'processed', 'invalid', 'archived')",
            name="submission_evidence_status",
        ),
        CheckConstraint(
            "raw_text is not null or file_artifact_id is not null or value_payload <> '{}'::jsonb",
            name="submission_evidence_has_payload",
        ),
        Index("ix_submission_evidence_submission", "submission_id"),
        Index("ix_submission_evidence_type", "evidence_type_id"),
        Index("ix_submission_evidence_file_artifact", "file_artifact_id"),
        Index("ix_submission_evidence_extraction", "evidence_extraction_id"),
    )
