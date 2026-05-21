import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class Rubric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubrics"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    rubric_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_types.id"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    draft_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    latest_version_number: Mapped[int | None] = mapped_column()

    versions: Mapped[list["RubricVersion"]] = relationship(back_populates="rubric")

    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'published', 'archived')",
            name="rubric_status",
        ),
        Index("ix_rubrics_organization_status", "organization_id", "status"),
        Index("ix_rubrics_type", "rubric_type_id"),
    )


class RubricVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubric_versions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False, default="1.0")
    rubric_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="published")

    rubric: Mapped[Rubric] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("rubric_id", "version_number"),
        CheckConstraint("version_number > 0", name="rubric_version_positive"),
        CheckConstraint(
            "status in ('published', 'archived')",
            name="rubric_version_status",
        ),
        Index("ix_rubric_versions_organization_status", "organization_id", "status"),
    )


class AnswerKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "answer_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    assessment_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_items.id"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    draft_key: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    latest_version_number: Mapped[int | None] = mapped_column()

    versions: Mapped[list["AnswerKeyVersion"]] = relationship(back_populates="answer_key")

    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'published', 'archived')",
            name="answer_key_status",
        ),
        Index("ix_answer_keys_organization_status", "organization_id", "status"),
        Index("ix_answer_keys_assessment_item", "assessment_item_id"),
    )


class AnswerKeyVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "answer_key_versions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    answer_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answer_keys.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False, default="1.0")
    key_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="published")

    answer_key: Mapped[AnswerKey] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("answer_key_id", "version_number"),
        CheckConstraint("version_number > 0", name="answer_key_version_positive"),
        CheckConstraint(
            "status in ('published', 'archived')",
            name="answer_key_version_status",
        ),
        Index("ix_answer_key_versions_organization_status", "organization_id", "status"),
    )
