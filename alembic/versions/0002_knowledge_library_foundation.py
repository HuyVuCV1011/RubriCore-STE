"""knowledge library foundation

Revision ID: 0002_knowledge_foundation
Revises: 0001_initial_database_foundation
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "0002_knowledge_foundation"
down_revision: str | None = "0001_initial_database_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACCESS_SCOPE_CHECK = "access_scope in ('private', 'course', 'organization', 'subject_pack', 'public_safe')"


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
    op.add_column(
        "file_artifacts",
        sa.Column(
            "access_scope",
            sa.String(length=40),
            server_default="organization",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_file_artifacts_file_artifact_access_scope"),
        "file_artifacts",
        ACCESS_SCOPE_CHECK,
    )
    op.create_index(
        "ix_file_artifacts_organization_scope",
        "file_artifacts",
        ["organization_id", "access_scope"],
    )
    op.alter_column("file_artifacts", "access_scope", server_default=None)

    op.create_table(
        "artifact_conversions",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_file_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("converted_file_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("conversion_type", sa.String(length=80), nullable=False),
        sa.Column("conversion_status", sa.String(length=40), nullable=False),
        sa.Column("converter_name", sa.String(length=160), nullable=True),
        sa.Column("converter_version", sa.String(length=80), nullable=True),
        sa.Column("conversion_schema_version", sa.String(length=80), nullable=False),
        sa.Column("access_scope", sa.String(length=40), nullable=False),
        jsonb_column("warnings"),
        sa.Column("error_message", sa.Text(), nullable=True),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint(
            "conversion_type in ('markdown', 'text', 'preview', 'metadata')",
            name=op.f("ck_artifact_conversions_artifact_conversion_type"),
        ),
        sa.CheckConstraint(
            "conversion_status in ('pending', 'running', 'completed', 'unsupported', 'failed')",
            name=op.f("ck_artifact_conversions_artifact_conversion_status"),
        ),
        sa.CheckConstraint(
            ACCESS_SCOPE_CHECK,
            name=op.f("ck_artifact_conversions_artifact_conversion_access_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["converted_file_artifact_id"],
            ["file_artifacts.id"],
            name=op.f("fk_artifact_conversions_converted_file_artifact_id_file_artifacts"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_artifact_conversions_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["source_file_artifact_id"],
            ["file_artifacts.id"],
            name=op.f("fk_artifact_conversions_source_file_artifact_id_file_artifacts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifact_conversions")),
    )
    op.create_index(
        "ix_artifact_conversions_converted",
        "artifact_conversions",
        ["converted_file_artifact_id"],
    )
    op.create_index(
        "ix_artifact_conversions_organization_status",
        "artifact_conversions",
        ["organization_id", "conversion_status"],
    )
    op.create_index(
        "ix_artifact_conversions_source",
        "artifact_conversions",
        ["source_file_artifact_id"],
    )
    op.create_index(
        "ix_artifact_conversions_source_type",
        "artifact_conversions",
        ["source_file_artifact_id", "conversion_type"],
    )

    op.create_table(
        "knowledge_sources",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("subject_pack_id", sa.Uuid(), nullable=True),
        sa.Column("source_file_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("converted_markdown_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("access_scope", sa.String(length=40), nullable=False),
        sa.Column("conversion_status", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("version_number > 0", name=op.f("ck_knowledge_sources_knowledge_source_version_positive")),
        sa.CheckConstraint(ACCESS_SCOPE_CHECK, name=op.f("ck_knowledge_sources_knowledge_source_access_scope")),
        sa.CheckConstraint(
            "conversion_status in ('pending', 'running', 'converted', 'unsupported', 'failed')",
            name=op.f("ck_knowledge_sources_knowledge_source_conversion_status"),
        ),
        sa.CheckConstraint(
            "status in ('draft', 'active', 'archived')",
            name=op.f("ck_knowledge_sources_knowledge_source_status"),
        ),
        sa.ForeignKeyConstraint(
            ["converted_markdown_artifact_id"],
            ["file_artifacts.id"],
            name=op.f("fk_knowledge_sources_converted_markdown_artifact_id_file_artifacts"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_knowledge_sources_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_knowledge_sources_owner_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["source_file_artifact_id"],
            ["file_artifacts.id"],
            name=op.f("fk_knowledge_sources_source_file_artifact_id_file_artifacts"),
        ),
        sa.ForeignKeyConstraint(
            ["subject_pack_id"],
            ["subject_packs.id"],
            name=op.f("fk_knowledge_sources_subject_pack_id_subject_packs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_sources")),
        sa.UniqueConstraint(
            "source_file_artifact_id",
            "version_number",
            name=op.f("uq_knowledge_sources_source_file_artifact_id"),
        ),
    )
    op.create_index(
        "ix_knowledge_sources_converted_artifact",
        "knowledge_sources",
        ["converted_markdown_artifact_id"],
    )
    op.create_index(
        "ix_knowledge_sources_organization_scope",
        "knowledge_sources",
        ["organization_id", "access_scope"],
    )
    op.create_index(
        "ix_knowledge_sources_organization_status",
        "knowledge_sources",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_knowledge_sources_source_artifact",
        "knowledge_sources",
        ["source_file_artifact_id"],
    )
    op.create_index(
        "ix_knowledge_sources_subject_pack",
        "knowledge_sources",
        ["subject_pack_id"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_sources")
    op.drop_table("artifact_conversions")
    op.drop_index("ix_file_artifacts_organization_scope", table_name="file_artifacts")
    op.drop_constraint(
        op.f("ck_file_artifacts_file_artifact_access_scope"),
        "file_artifacts",
        type_="check",
    )
    op.drop_column("file_artifacts", "access_scope")
