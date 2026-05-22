import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
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
    slug: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    draft_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    latest_version_number: Mapped[int | None] = mapped_column()

    versions: Mapped[list["RubricVersion"]] = relationship(back_populates="rubric")

    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'published', 'archived')",
            name="rubric_status",
        ),
        UniqueConstraint("organization_id", "slug", name="uq_rubrics_organization_slug"),
        Index("ix_rubrics_organization_status", "organization_id", "status"),
        Index("ix_rubrics_organization_slug", "organization_id", "slug"),
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
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="published")

    rubric: Mapped[Rubric] = relationship(back_populates="versions")
    criteria: Mapped[list["RubricCriterion"]] = relationship(
        back_populates="rubric_version",
        order_by="RubricCriterion.position",
    )
    performance_levels: Mapped[list["PerformanceLevel"]] = relationship(
        back_populates="rubric_version",
        order_by="PerformanceLevel.position",
    )
    descriptors: Mapped[list["RubricDescriptor"]] = relationship(back_populates="rubric_version")
    bindings: Mapped[list["RubricBinding"]] = relationship(back_populates="rubric_version")

    __table_args__ = (
        UniqueConstraint("rubric_id", "version_number"),
        CheckConstraint("version_number > 0", name="rubric_version_positive"),
        CheckConstraint(
            "status in ('published', 'archived')",
            name="rubric_version_status",
        ),
        Index("ix_rubric_versions_organization_status", "organization_id", "status"),
    )


class RubricCriterion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubric_criteria"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_versions.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    evaluation_hints: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    rubric_version: Mapped[RubricVersion] = relationship(back_populates="criteria")
    descriptors: Mapped[list["RubricDescriptor"]] = relationship(back_populates="criterion")

    __table_args__ = (
        UniqueConstraint("rubric_version_id", "key", name="uq_rubric_criteria_version_key"),
        UniqueConstraint("rubric_version_id", "position", name="uq_rubric_criteria_version_position"),
        CheckConstraint("weight is null or weight > 0", name="rubric_criterion_weight_positive"),
        Index("ix_rubric_criteria_version_position", "rubric_version_id", "position"),
        Index("ix_rubric_criteria_organization", "organization_id"),
    )


class PerformanceLevel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "performance_levels"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_versions.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    score: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    rubric_version: Mapped[RubricVersion] = relationship(back_populates="performance_levels")
    descriptors: Mapped[list["RubricDescriptor"]] = relationship(back_populates="performance_level")

    __table_args__ = (
        UniqueConstraint("rubric_version_id", "key", name="uq_performance_levels_version_key"),
        UniqueConstraint("rubric_version_id", "position", name="uq_performance_levels_version_position"),
        CheckConstraint("score >= 0", name="performance_level_score_nonnegative"),
        Index("ix_performance_levels_version_position", "rubric_version_id", "position"),
        Index("ix_performance_levels_organization", "organization_id"),
    )


class RubricDescriptor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubric_descriptors"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_versions.id"), nullable=False)
    criterion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_criteria.id"), nullable=False)
    performance_level_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("performance_levels.id"), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(160), nullable=False)
    performance_level_key: Mapped[str] = mapped_column(String(160), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_hints: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    rubric_version: Mapped[RubricVersion] = relationship(back_populates="descriptors")
    criterion: Mapped[RubricCriterion] = relationship(back_populates="descriptors")
    performance_level: Mapped[PerformanceLevel] = relationship(back_populates="descriptors")

    __table_args__ = (
        UniqueConstraint("criterion_id", "performance_level_id", name="uq_rubric_descriptors_criterion_level"),
        UniqueConstraint(
            "rubric_version_id",
            "criterion_key",
            "performance_level_key",
            name="uq_rubric_descriptors_version_keys",
        ),
        Index("ix_rubric_descriptors_version", "rubric_version_id"),
        Index("ix_rubric_descriptors_criterion", "criterion_id"),
        Index("ix_rubric_descriptors_level", "performance_level_id"),
    )


class RubricBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubric_bindings"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_versions.id"), nullable=False)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id"))
    assessment_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessment_items.id"))
    external_context_key: Mapped[str | None] = mapped_column(String(255))
    context_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    bound_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="teacher")
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    rubric_version: Mapped[RubricVersion] = relationship(back_populates="bindings")

    __table_args__ = (
        CheckConstraint(
            "context_type in ('assessment', 'assessment_item', 'evaluation_context')",
            name="rubric_binding_context_type",
        ),
        CheckConstraint(
            "status in ('active', 'superseded', 'archived')",
            name="rubric_binding_status",
        ),
        CheckConstraint(
            "source in ('teacher', 'system', 'fixture_import', 'api_import')",
            name="rubric_binding_source",
        ),
        CheckConstraint(
            "assessment_id is not null or assessment_item_id is not null or external_context_key is not null",
            name="rubric_binding_has_context",
        ),
        Index("ix_rubric_bindings_organization_status", "organization_id", "status"),
        Index("ix_rubric_bindings_rubric_version", "rubric_version_id"),
        Index("ix_rubric_bindings_assessment", "assessment_id"),
        Index("ix_rubric_bindings_assessment_item", "assessment_item_id"),
        Index("ix_rubric_bindings_external_context", "external_context_key"),
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
