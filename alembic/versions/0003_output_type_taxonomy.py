"""output type taxonomy

Revision ID: 0003_output_type_taxonomy
Revises: 0002_knowledge_foundation
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "0003_output_type_taxonomy"
down_revision: str | None = "0002_knowledge_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), nullable=False)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def jsonb_column(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "output_types",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        jsonb_column("config"),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "status in ('active', 'archived')",
            name=op.f("ck_output_types_output_type_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_output_types_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_output_types")),
        sa.UniqueConstraint("organization_id", "key", name=op.f("uq_output_types_organization_id")),
    )
    op.create_index("ix_output_types_organization_status", "output_types", ["organization_id", "status"])

    op.add_column("assessment_items", sa.Column("output_type_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_assessment_items_output_type_id_output_types"),
        "assessment_items",
        "output_types",
        ["output_type_id"],
        ["id"],
    )
    op.create_index("ix_assessment_items_output_type", "assessment_items", ["output_type_id"])


def downgrade() -> None:
    op.drop_index("ix_assessment_items_output_type", table_name="assessment_items")
    op.drop_constraint(
        op.f("fk_assessment_items_output_type_id_output_types"),
        "assessment_items",
        type_="foreignkey",
    )
    op.drop_column("assessment_items", "output_type_id")
    op.drop_table("output_types")
