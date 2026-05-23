import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


KNOWLEDGE_ACCESS_SCOPE_CHECK = "access_scope in ('private', 'course', 'organization', 'subject_pack', 'public_safe')"


class KnowledgeSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    subject_pack_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subject_packs.id"))
    source_file_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_artifacts.id"), nullable=False)
    converted_markdown_artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("file_artifacts.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False, default=1)
    access_scope: Mapped[str] = mapped_column(String(40), nullable=False, default="organization")
    conversion_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    summary: Mapped[str | None] = mapped_column(Text)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("source_file_artifact_id", "version_number"),
        CheckConstraint("version_number > 0", name="knowledge_source_version_positive"),
        CheckConstraint(KNOWLEDGE_ACCESS_SCOPE_CHECK, name="knowledge_source_access_scope"),
        CheckConstraint(
            "conversion_status in ('pending', 'running', 'converted', 'unsupported', 'failed')",
            name="knowledge_source_conversion_status",
        ),
        CheckConstraint(
            "status in ('draft', 'active', 'archived')",
            name="knowledge_source_status",
        ),
        Index("ix_knowledge_sources_organization_status", "organization_id", "status"),
        Index("ix_knowledge_sources_organization_scope", "organization_id", "access_scope"),
        Index("ix_knowledge_sources_subject_pack", "subject_pack_id"),
        Index("ix_knowledge_sources_source_artifact", "source_file_artifact_id"),
        Index("ix_knowledge_sources_converted_artifact", "converted_markdown_artifact_id"),
    )


class KnowledgeChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    knowledge_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_sources.id"), nullable=False)
    converted_markdown_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_artifacts.id"), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    chunk_key: Mapped[str] = mapped_column(String(160), nullable=False)
    heading_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    character_count: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("knowledge_source_id", "position", name="uq_knowledge_chunks_source_position"),
        UniqueConstraint("knowledge_source_id", "chunk_key", name="uq_knowledge_chunks_source_key"),
        CheckConstraint("position >= 0", name="knowledge_chunk_position_nonnegative"),
        CheckConstraint("character_count >= 0", name="knowledge_chunk_character_count_nonnegative"),
        CheckConstraint(
            "status in ('active', 'superseded', 'archived')",
            name="knowledge_chunk_status",
        ),
        Index("ix_knowledge_chunks_organization_status", "organization_id", "status"),
        Index("ix_knowledge_chunks_source_position", "knowledge_source_id", "position"),
        Index("ix_knowledge_chunks_converted_artifact", "converted_markdown_artifact_id"),
        Index("ix_knowledge_chunks_content_hash", "content_hash"),
    )


class RubricSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubric_suggestions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    target_rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id"), nullable=False)
    target_assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id"))
    target_assessment_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessment_items.id"))
    suggestion_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    suggestion_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    accepted_payload: Mapped[dict | None] = mapped_column(JSONB)
    source_citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "suggestion_type in ('criterion', 'descriptor', 'feedback_theme', 'accepted_variant', 'rubric_note')",
            name="rubric_suggestion_type",
        ),
        CheckConstraint(
            "status in ('draft', 'accepted', 'rejected', 'superseded')",
            name="rubric_suggestion_status",
        ),
        Index("ix_rubric_suggestions_organization_status", "organization_id", "status"),
        Index("ix_rubric_suggestions_target_rubric", "target_rubric_id"),
        Index("ix_rubric_suggestions_assessment", "target_assessment_id"),
        Index("ix_rubric_suggestions_assessment_item", "target_assessment_item_id"),
        Index("ix_rubric_suggestions_created_by", "created_by_user_id"),
        Index("ix_rubric_suggestions_reviewed_by", "reviewed_by_user_id"),
    )
