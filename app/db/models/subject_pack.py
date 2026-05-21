import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class SubjectPack(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subject_packs"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False, default="1.0")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("organization_id", "key"),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="subject_pack_status",
        ),
        Index("ix_subject_packs_organization_status", "organization_id", "status"),
    )
