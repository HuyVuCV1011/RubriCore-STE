import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class Assessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessments"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    assessment_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_types.id"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    items: Mapped[list["AssessmentItem"]] = relationship(back_populates="assessment")

    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'active', 'archived')",
            name="assessment_status",
        ),
        Index("ix_assessments_organization_status", "organization_id", "status"),
        Index("ix_assessments_type", "assessment_type_id"),
    )


class AssessmentItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    assessment_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_types.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    item_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    assessment: Mapped[Assessment] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'active', 'archived')",
            name="assessment_item_status",
        ),
        Index("ix_assessment_items_organization_status", "organization_id", "status"),
        Index("ix_assessment_items_assessment_position", "assessment_id", "position"),
        Index("ix_assessment_items_type", "assessment_type_id"),
    )
