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
