import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class AssessmentType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_types"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("organization_id", "key"),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="assessment_type_status",
        ),
        Index("ix_assessment_types_organization_status", "organization_id", "status"),
    )


class EvidenceType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_types"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("organization_id", "key"),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="evidence_type_status",
        ),
        Index("ix_evidence_types_organization_status", "organization_id", "status"),
    )


class OutputType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "output_types"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("organization_id", "key"),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="output_type_status",
        ),
        Index("ix_output_types_organization_status", "organization_id", "status"),
    )


class RubricType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubric_types"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("organization_id", "key"),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="rubric_type_status",
        ),
        Index("ix_rubric_types_organization_status", "organization_id", "status"),
    )


class FilePurpose(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_purposes"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("organization_id", "key"),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="file_purpose_status",
        ),
        Index("ix_file_purposes_organization_status", "organization_id", "status"),
    )
