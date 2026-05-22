"""artifact provenance

Revision ID: 0004_artifact_provenance
Revises: 0003_output_type_taxonomy
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0004_artifact_provenance"
down_revision: str | None = "0003_output_type_taxonomy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ARTIFACT_SOURCE_TYPE_CHECK = (
    "source_type in ("
    "'unknown', 'web_upload', 'fixture_import', 'teacher_import', "
    "'api_import', 'batch_import', 'system_conversion', 'knowledge_library'"
    ")"
)

ARTIFACT_SOURCE_FORMAT_CHECK = (
    "source_format in ("
    "'unknown', 'text', 'markdown', 'python', 'javascript', 'typescript', "
    "'sql', 'notebook', 'pdf', 'doc', 'docx', 'rtf', 'csv', 'tsv', 'xlsx', "
    "'json', 'xml', 'image', 'audio', 'video', 'archive'"
    ")"
)


def upgrade() -> None:
    op.add_column("file_artifacts", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.add_column("file_artifacts", sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "file_artifacts",
        sa.Column("source_type", sa.String(length=80), server_default="unknown", nullable=False),
    )
    op.add_column(
        "file_artifacts",
        sa.Column("source_format", sa.String(length=80), server_default="unknown", nullable=False),
    )
    op.add_column(
        "file_artifacts",
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.execute(
        """
        update file_artifacts
        set source_type = case
            when import_source = 'public_fixture' then 'fixture_import'
            when import_source = 'knowledge_library' then 'knowledge_library'
            when import_source = 'knowledge_library_conversion' then 'system_conversion'
            else 'unknown'
        end
        """
    )
    op.execute(
        """
        update file_artifacts
        set source_format = case lower(coalesce(file_extension, ''))
            when 'md' then 'markdown'
            when 'markdown' then 'markdown'
            when 'txt' then 'text'
            when 'rtf' then 'rtf'
            when 'pdf' then 'pdf'
            when 'doc' then 'doc'
            when 'docx' then 'docx'
            when 'py' then 'python'
            when 'js' then 'javascript'
            when 'ts' then 'typescript'
            when 'sql' then 'sql'
            when 'ipynb' then 'notebook'
            when 'csv' then 'csv'
            when 'tsv' then 'tsv'
            when 'xlsx' then 'xlsx'
            when 'json' then 'json'
            when 'xml' then 'xml'
            when 'zip' then 'archive'
            else 'unknown'
        end
        """
    )

    op.create_foreign_key(
        op.f("fk_file_artifacts_owner_user_id_users"),
        "file_artifacts",
        "users",
        ["owner_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_file_artifacts_uploaded_by_user_id_users"),
        "file_artifacts",
        "users",
        ["uploaded_by_user_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_file_artifacts_file_artifact_source_type"),
        "file_artifacts",
        ARTIFACT_SOURCE_TYPE_CHECK,
    )
    op.create_check_constraint(
        op.f("ck_file_artifacts_file_artifact_source_format"),
        "file_artifacts",
        ARTIFACT_SOURCE_FORMAT_CHECK,
    )
    op.create_index("ix_file_artifacts_owner", "file_artifacts", ["owner_user_id"])
    op.create_index("ix_file_artifacts_uploaded_by", "file_artifacts", ["uploaded_by_user_id"])
    op.create_index("ix_file_artifacts_source_type", "file_artifacts", ["source_type"])
    op.create_index("ix_file_artifacts_uploaded_at", "file_artifacts", ["uploaded_at"])
    op.alter_column("file_artifacts", "source_type", server_default=None)
    op.alter_column("file_artifacts", "source_format", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_file_artifacts_uploaded_at", table_name="file_artifacts")
    op.drop_index("ix_file_artifacts_source_type", table_name="file_artifacts")
    op.drop_index("ix_file_artifacts_uploaded_by", table_name="file_artifacts")
    op.drop_index("ix_file_artifacts_owner", table_name="file_artifacts")
    op.drop_constraint(
        op.f("ck_file_artifacts_file_artifact_source_format"),
        "file_artifacts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_file_artifacts_file_artifact_source_type"),
        "file_artifacts",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_file_artifacts_uploaded_by_user_id_users"),
        "file_artifacts",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_file_artifacts_owner_user_id_users"),
        "file_artifacts",
        type_="foreignkey",
    )
    op.drop_column("file_artifacts", "uploaded_at")
    op.drop_column("file_artifacts", "source_format")
    op.drop_column("file_artifacts", "source_type")
    op.drop_column("file_artifacts", "uploaded_by_user_id")
    op.drop_column("file_artifacts", "owner_user_id")
