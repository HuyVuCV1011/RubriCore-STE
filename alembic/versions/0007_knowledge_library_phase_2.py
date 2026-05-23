"""knowledge library phase 2

Revision ID: 0007_knowledge_library_phase_2
Revises: 0006_answer_lifecycle
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "0007_knowledge_library_phase_2"
down_revision: str | None = "0006_answer_lifecycle"
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
        "knowledge_chunks",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_source_id", sa.Uuid(), nullable=False),
        sa.Column("converted_markdown_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("chunk_key", sa.String(length=160), nullable=False),
        jsonb_column("heading_path"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("position >= 0", name=op.f("ck_knowledge_chunks_knowledge_chunk_position_nonnegative")),
        sa.CheckConstraint(
            "character_count >= 0",
            name=op.f("ck_knowledge_chunks_knowledge_chunk_character_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "status in ('active', 'superseded', 'archived')",
            name=op.f("ck_knowledge_chunks_knowledge_chunk_status"),
        ),
        sa.ForeignKeyConstraint(
            ["converted_markdown_artifact_id"],
            ["file_artifacts.id"],
            name=op.f("fk_knowledge_chunks_converted_markdown_artifact_id_file_artifacts"),
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_source_id"],
            ["knowledge_sources.id"],
            name=op.f("fk_knowledge_chunks_knowledge_source_id_knowledge_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_knowledge_chunks_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "knowledge_source_id",
            "chunk_key",
            name=op.f("uq_knowledge_chunks_source_key"),
        ),
        sa.UniqueConstraint(
            "knowledge_source_id",
            "position",
            name=op.f("uq_knowledge_chunks_source_position"),
        ),
    )
    op.create_index("ix_knowledge_chunks_content_hash", "knowledge_chunks", ["content_hash"])
    op.create_index(
        "ix_knowledge_chunks_converted_artifact",
        "knowledge_chunks",
        ["converted_markdown_artifact_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_organization_status",
        "knowledge_chunks",
        ["organization_id", "status"],
    )
    op.create_index("ix_knowledge_chunks_source_position", "knowledge_chunks", ["knowledge_source_id", "position"])

    op.create_table(
        "rubric_suggestions",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("target_rubric_id", sa.Uuid(), nullable=False),
        sa.Column("target_assessment_id", sa.Uuid(), nullable=True),
        sa.Column("target_assessment_item_id", sa.Uuid(), nullable=True),
        sa.Column("suggestion_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        jsonb_column("suggestion_payload"),
        jsonb_column("accepted_payload", nullable=True),
        jsonb_column("source_citations"),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint(
            "suggestion_type in ('criterion', 'descriptor', 'feedback_theme', 'accepted_variant', 'rubric_note')",
            name=op.f("ck_rubric_suggestions_rubric_suggestion_type"),
        ),
        sa.CheckConstraint(
            "status in ('draft', 'accepted', 'rejected', 'superseded')",
            name=op.f("ck_rubric_suggestions_rubric_suggestion_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_rubric_suggestions_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_rubric_suggestions_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name=op.f("fk_rubric_suggestions_reviewed_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["target_assessment_id"],
            ["assessments.id"],
            name=op.f("fk_rubric_suggestions_target_assessment_id_assessments"),
        ),
        sa.ForeignKeyConstraint(
            ["target_assessment_item_id"],
            ["assessment_items.id"],
            name=op.f("fk_rubric_suggestions_target_assessment_item_id_assessment_items"),
        ),
        sa.ForeignKeyConstraint(
            ["target_rubric_id"],
            ["rubrics.id"],
            name=op.f("fk_rubric_suggestions_target_rubric_id_rubrics"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_suggestions")),
    )
    op.create_index(
        "ix_rubric_suggestions_assessment",
        "rubric_suggestions",
        ["target_assessment_id"],
    )
    op.create_index(
        "ix_rubric_suggestions_assessment_item",
        "rubric_suggestions",
        ["target_assessment_item_id"],
    )
    op.create_index(
        "ix_rubric_suggestions_created_by",
        "rubric_suggestions",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_rubric_suggestions_organization_status",
        "rubric_suggestions",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_rubric_suggestions_reviewed_by",
        "rubric_suggestions",
        ["reviewed_by_user_id"],
    )
    op.create_index(
        "ix_rubric_suggestions_target_rubric",
        "rubric_suggestions",
        ["target_rubric_id"],
    )


def downgrade() -> None:
    op.drop_table("rubric_suggestions")
    op.drop_table("knowledge_chunks")
