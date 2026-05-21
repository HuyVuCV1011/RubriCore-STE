import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    learners: Mapped[list["Learner"]] = relationship(back_populates="organization")

    __table_args__ = (
        UniqueConstraint("slug"),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="organization_status",
        ),
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    organization: Mapped[Organization] = relationship(back_populates="users")

    __table_args__ = (
        UniqueConstraint("organization_id", "email"),
        CheckConstraint(
            "role in ('admin', 'teacher', 'reviewer', 'learner', 'system')",
            name="user_role",
        ),
        CheckConstraint(
            "status in ('active', 'inactive', 'archived')",
            name="user_status",
        ),
        Index("ix_users_organization_status", "organization_id", "status"),
    )


class Learner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "learners"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
    )
    external_ref: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")

    organization: Mapped[Organization] = relationship(back_populates="learners")

    __table_args__ = (
        UniqueConstraint("organization_id", "external_ref"),
        CheckConstraint(
            "status in ('active', 'inactive', 'archived')",
            name="learner_status",
        ),
        Index("ix_learners_organization_status", "organization_id", "status"),
    )
