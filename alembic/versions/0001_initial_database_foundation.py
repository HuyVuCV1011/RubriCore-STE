"""initial database foundation

Revision ID: 0001_initial_database_foundation
Revises:
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "0001_initial_database_foundation"
down_revision: str | None = None
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
        "organizations",
        uuid_pk(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.CheckConstraint("status in ('active', 'archived')", name=op.f("ck_organizations_organization_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )

    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.CheckConstraint("role in ('admin', 'teacher', 'reviewer', 'learner', 'system')", name=op.f("ck_users_user_role")),
        sa.CheckConstraint("status in ('active', 'inactive', 'archived')", name=op.f("ck_users_user_status")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_users_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("organization_id", "email", name=op.f("uq_users_organization_id")),
    )
    op.create_index("ix_users_organization_status", "users", ["organization_id", "status"])

    op.create_table(
        "learners",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.CheckConstraint("status in ('active', 'inactive', 'archived')", name=op.f("ck_learners_learner_status")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_learners_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learners")),
        sa.UniqueConstraint("organization_id", "external_ref", name=op.f("uq_learners_organization_id")),
    )
    op.create_index("ix_learners_organization_status", "learners", ["organization_id", "status"])

    for table_name, check_name in (
        ("assessment_types", "assessment_type_status"),
        ("evidence_types", "evidence_type_status"),
        ("rubric_types", "rubric_type_status"),
        ("file_purposes", "file_purpose_status"),
    ):
        op.create_table(
            table_name,
            uuid_pk(),
            sa.Column("organization_id", sa.Uuid(), nullable=True),
            sa.Column("key", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(length=1000), nullable=True),
            jsonb_column("config"),
            sa.Column("status", sa.String(length=40), nullable=False),
            *timestamps(),
            sa.CheckConstraint("status in ('active', 'archived')", name=op.f(f"ck_{table_name}_{check_name}")),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f(f"fk_{table_name}_organization_id_organizations")),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table_name}")),
            sa.UniqueConstraint("organization_id", "key", name=op.f(f"uq_{table_name}_organization_id")),
        )
        op.create_index(f"ix_{table_name}_organization_status", table_name, ["organization_id", "status"])

    op.create_table(
        "assessments",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_type_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("settings"),
        *timestamps(),
        sa.CheckConstraint("status in ('draft', 'active', 'archived')", name=op.f("ck_assessments_assessment_status")),
        sa.ForeignKeyConstraint(["assessment_type_id"], ["assessment_types.id"], name=op.f("fk_assessments_assessment_type_id_assessment_types")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_assessments_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_assessments_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
    )
    op.create_index("ix_assessments_organization_status", "assessments", ["organization_id", "status"])
    op.create_index("ix_assessments_type", "assessments", ["assessment_type_id"])

    op.create_table(
        "assessment_items",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_type_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("item_config"),
        *timestamps(),
        sa.CheckConstraint("status in ('draft', 'active', 'archived')", name=op.f("ck_assessment_items_assessment_item_status")),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], name=op.f("fk_assessment_items_assessment_id_assessments")),
        sa.ForeignKeyConstraint(["assessment_type_id"], ["assessment_types.id"], name=op.f("fk_assessment_items_assessment_type_id_assessment_types")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_assessment_items_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_items")),
    )
    op.create_index("ix_assessment_items_assessment_position", "assessment_items", ["assessment_id", "position"])
    op.create_index("ix_assessment_items_organization_status", "assessment_items", ["organization_id", "status"])
    op.create_index("ix_assessment_items_type", "assessment_items", ["assessment_type_id"])

    op.create_table(
        "file_artifacts",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("file_purpose_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("normalized_filename", sa.String(length=500), nullable=False),
        sa.Column("file_extension", sa.String(length=40), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("detected_file_category", sa.String(length=80), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("storage_uri", sa.String(length=1000), nullable=False),
        sa.Column("import_source", sa.String(length=80), nullable=False),
        sa.Column("parser_support_status", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("file_size_bytes is null or file_size_bytes >= 0", name=op.f("ck_file_artifacts_file_artifact_size_nonnegative")),
        sa.CheckConstraint("parser_support_status in ('unknown', 'supported', 'unsupported', 'failed')", name=op.f("ck_file_artifacts_file_artifact_parser_support_status")),
        sa.CheckConstraint("status in ('active', 'archived', 'deleted')", name=op.f("ck_file_artifacts_file_artifact_status")),
        sa.ForeignKeyConstraint(["file_purpose_id"], ["file_purposes.id"], name=op.f("fk_file_artifacts_file_purpose_id_file_purposes")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_file_artifacts_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_artifacts")),
    )
    op.create_index("ix_file_artifacts_checksum", "file_artifacts", ["checksum_sha256"])
    op.create_index("ix_file_artifacts_organization_purpose", "file_artifacts", ["organization_id", "file_purpose_id"])
    op.create_index("ix_file_artifacts_organization_status", "file_artifacts", ["organization_id", "status"])
    op.create_index("ix_file_artifacts_purpose", "file_artifacts", ["file_purpose_id"])

    op.create_table(
        "assessment_materials",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("assessment_item_id", sa.Uuid(), nullable=True),
        sa.Column("file_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("assessment_id is not null or assessment_item_id is not null", name=op.f("ck_assessment_materials_assessment_material_has_context")),
        sa.CheckConstraint("status in ('active', 'archived')", name=op.f("ck_assessment_materials_assessment_material_status")),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], name=op.f("fk_assessment_materials_assessment_id_assessments")),
        sa.ForeignKeyConstraint(["assessment_item_id"], ["assessment_items.id"], name=op.f("fk_assessment_materials_assessment_item_id_assessment_items")),
        sa.ForeignKeyConstraint(["file_artifact_id"], ["file_artifacts.id"], name=op.f("fk_assessment_materials_file_artifact_id_file_artifacts")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_assessment_materials_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_materials")),
    )
    op.create_index("ix_assessment_materials_assessment", "assessment_materials", ["assessment_id"])
    op.create_index("ix_assessment_materials_assessment_item", "assessment_materials", ["assessment_item_id"])
    op.create_index("ix_assessment_materials_file_artifact", "assessment_materials", ["file_artifact_id"])

    op.create_table(
        "rubrics",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_type_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("draft_schema"),
        sa.Column("latest_version_number", sa.Integer(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status in ('draft', 'published', 'archived')", name=op.f("ck_rubrics_rubric_status")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_rubrics_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_rubrics_organization_id_organizations")),
        sa.ForeignKeyConstraint(["rubric_type_id"], ["rubric_types.id"], name=op.f("fk_rubrics_rubric_type_id_rubric_types")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubrics")),
    )
    op.create_index("ix_rubrics_organization_status", "rubrics", ["organization_id", "status"])
    op.create_index("ix_rubrics_type", "rubrics", ["rubric_type_id"])

    op.create_table(
        "rubric_versions",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        jsonb_column("rubric_schema"),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.CheckConstraint("status in ('published', 'archived')", name=op.f("ck_rubric_versions_rubric_version_status")),
        sa.CheckConstraint("version_number > 0", name=op.f("ck_rubric_versions_rubric_version_positive")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_rubric_versions_organization_id_organizations")),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], name=op.f("fk_rubric_versions_published_by_user_id_users")),
        sa.ForeignKeyConstraint(["rubric_id"], ["rubrics.id"], name=op.f("fk_rubric_versions_rubric_id_rubrics")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_versions")),
        sa.UniqueConstraint("rubric_id", "version_number", name=op.f("uq_rubric_versions_rubric_id")),
    )
    op.create_index("ix_rubric_versions_organization_status", "rubric_versions", ["organization_id", "status"])

    op.create_table(
        "answer_keys",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_item_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("draft_key"),
        sa.Column("latest_version_number", sa.Integer(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("status in ('draft', 'published', 'archived')", name=op.f("ck_answer_keys_answer_key_status")),
        sa.ForeignKeyConstraint(["assessment_item_id"], ["assessment_items.id"], name=op.f("fk_answer_keys_assessment_item_id_assessment_items")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_answer_keys_created_by_user_id_users")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_answer_keys_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_keys")),
    )
    op.create_index("ix_answer_keys_assessment_item", "answer_keys", ["assessment_item_id"])
    op.create_index("ix_answer_keys_organization_status", "answer_keys", ["organization_id", "status"])

    op.create_table(
        "answer_key_versions",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("answer_key_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        jsonb_column("key_payload"),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.CheckConstraint("status in ('published', 'archived')", name=op.f("ck_answer_key_versions_answer_key_version_status")),
        sa.CheckConstraint("version_number > 0", name=op.f("ck_answer_key_versions_answer_key_version_positive")),
        sa.ForeignKeyConstraint(["answer_key_id"], ["answer_keys.id"], name=op.f("fk_answer_key_versions_answer_key_id_answer_keys")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_answer_key_versions_organization_id_organizations")),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], name=op.f("fk_answer_key_versions_published_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_key_versions")),
        sa.UniqueConstraint("answer_key_id", "version_number", name=op.f("uq_answer_key_versions_answer_key_id")),
    )
    op.create_index("ix_answer_key_versions_organization_status", "answer_key_versions", ["organization_id", "status"])

    op.create_table(
        "answer_key_materials",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("answer_key_id", sa.Uuid(), nullable=True),
        sa.Column("answer_key_version_id", sa.Uuid(), nullable=True),
        sa.Column("file_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("answer_key_id is not null or answer_key_version_id is not null", name=op.f("ck_answer_key_materials_answer_key_material_has_context")),
        sa.CheckConstraint("status in ('active', 'archived')", name=op.f("ck_answer_key_materials_answer_key_material_status")),
        sa.ForeignKeyConstraint(["answer_key_id"], ["answer_keys.id"], name=op.f("fk_answer_key_materials_answer_key_id_answer_keys")),
        sa.ForeignKeyConstraint(["answer_key_version_id"], ["answer_key_versions.id"], name=op.f("fk_answer_key_materials_answer_key_version_id_answer_key_versions")),
        sa.ForeignKeyConstraint(["file_artifact_id"], ["file_artifacts.id"], name=op.f("fk_answer_key_materials_file_artifact_id_file_artifacts")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_answer_key_materials_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_key_materials")),
    )
    op.create_index("ix_answer_key_materials_answer_key", "answer_key_materials", ["answer_key_id"])
    op.create_index("ix_answer_key_materials_answer_key_version", "answer_key_materials", ["answer_key_version_id"])
    op.create_index("ix_answer_key_materials_file_artifact", "answer_key_materials", ["file_artifact_id"])

    op.create_table(
        "submissions",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("assessment_item_id", sa.Uuid(), nullable=True),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("assessment_id is not null or assessment_item_id is not null", name=op.f("ck_submissions_submission_has_assessment_context")),
        sa.CheckConstraint("status in ('draft', 'submitted', 'processing', 'graded', 'returned', 'archived')", name=op.f("ck_submissions_submission_status")),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], name=op.f("fk_submissions_assessment_id_assessments")),
        sa.ForeignKeyConstraint(["assessment_item_id"], ["assessment_items.id"], name=op.f("fk_submissions_assessment_item_id_assessment_items")),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.id"], name=op.f("fk_submissions_learner_id_learners")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_submissions_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )
    op.create_index("ix_submissions_assessment_item_learner", "submissions", ["assessment_item_id", "learner_id"])
    op.create_index("ix_submissions_assessment_learner", "submissions", ["assessment_id", "learner_id"])
    op.create_index("ix_submissions_organization_status", "submissions", ["organization_id", "status"])

    op.create_table(
        "grading_runs",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=True),
        sa.Column("answer_key_version_id", sa.Uuid(), nullable=True),
        sa.Column("triggered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_source", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("grading_policy_version", sa.String(length=80), nullable=True),
        jsonb_column("context_payload"),
        *timestamps(),
        sa.CheckConstraint("status in ('queued', 'running', 'completed', 'failed', 'cancelled')", name=op.f("ck_grading_runs_grading_run_status")),
        sa.ForeignKeyConstraint(["answer_key_version_id"], ["answer_key_versions.id"], name=op.f("fk_grading_runs_answer_key_version_id_answer_key_versions")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_grading_runs_organization_id_organizations")),
        sa.ForeignKeyConstraint(["rubric_version_id"], ["rubric_versions.id"], name=op.f("fk_grading_runs_rubric_version_id_rubric_versions")),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name=op.f("fk_grading_runs_submission_id_submissions")),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], name=op.f("fk_grading_runs_triggered_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_runs")),
    )
    op.create_index("ix_grading_runs_answer_key_version", "grading_runs", ["answer_key_version_id"])
    op.create_index("ix_grading_runs_organization_status", "grading_runs", ["organization_id", "status"])
    op.create_index("ix_grading_runs_rubric_version", "grading_runs", ["rubric_version_id"])
    op.create_index("ix_grading_runs_submission_status", "grading_runs", ["submission_id", "status"])

    op.create_table(
        "grading_results",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("grading_run_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=True),
        sa.Column("answer_key_version_id", sa.Uuid(), nullable=True),
        sa.Column("result_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("total_score", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("max_score", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        jsonb_column("explanation_payload"),
        *timestamps(),
        sa.CheckConstraint("confidence is null or (confidence >= 0 and confidence <= 1)", name=op.f("ck_grading_results_grading_result_confidence_range")),
        sa.CheckConstraint("result_type in ('proposed', 'final', 'reviewed', 'overridden')", name=op.f("ck_grading_results_grading_result_type")),
        sa.CheckConstraint("status in ('proposed', 'needs_review', 'finalized', 'superseded')", name=op.f("ck_grading_results_grading_result_status")),
        sa.ForeignKeyConstraint(["answer_key_version_id"], ["answer_key_versions.id"], name=op.f("fk_grading_results_answer_key_version_id_answer_key_versions")),
        sa.ForeignKeyConstraint(["grading_run_id"], ["grading_runs.id"], name=op.f("fk_grading_results_grading_run_id_grading_runs")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_grading_results_organization_id_organizations")),
        sa.ForeignKeyConstraint(["rubric_version_id"], ["rubric_versions.id"], name=op.f("fk_grading_results_rubric_version_id_rubric_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_results")),
    )
    op.create_index("ix_grading_results_answer_key_version", "grading_results", ["answer_key_version_id"])
    op.create_index("ix_grading_results_grading_run", "grading_results", ["grading_run_id"])
    op.create_index("ix_grading_results_organization_status", "grading_results", ["organization_id", "status"])
    op.create_index("ix_grading_results_rubric_version", "grading_results", ["rubric_version_id"])

    op.create_table(
        "evidence_extractions",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("file_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("output_file_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("extraction_type", sa.String(length=80), nullable=False),
        sa.Column("extraction_status", sa.String(length=40), nullable=False),
        sa.Column("parser_name", sa.String(length=160), nullable=True),
        sa.Column("parser_version", sa.String(length=80), nullable=True),
        sa.Column("extraction_schema_version", sa.String(length=80), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        jsonb_column("extracted_metadata"),
        jsonb_column("warnings"),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("extraction_status in ('pending', 'running', 'completed', 'unsupported', 'failed')", name=op.f("ck_evidence_extractions_evidence_extraction_status")),
        sa.ForeignKeyConstraint(["file_artifact_id"], ["file_artifacts.id"], name=op.f("fk_evidence_extractions_file_artifact_id_file_artifacts")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_evidence_extractions_organization_id_organizations")),
        sa.ForeignKeyConstraint(["output_file_artifact_id"], ["file_artifacts.id"], name=op.f("fk_evidence_extractions_output_file_artifact_id_file_artifacts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_extractions")),
    )
    op.create_index("ix_evidence_extractions_artifact_status", "evidence_extractions", ["file_artifact_id", "extraction_status"])
    op.create_index("ix_evidence_extractions_file_artifact", "evidence_extractions", ["file_artifact_id"])
    op.create_index("ix_evidence_extractions_organization", "evidence_extractions", ["organization_id"])
    op.create_index("ix_evidence_extractions_status", "evidence_extractions", ["extraction_status"])

    op.create_table(
        "submission_evidence",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_type_id", sa.Uuid(), nullable=False),
        sa.Column("file_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_extraction_id", sa.Uuid(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        jsonb_column("value_payload"),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.CheckConstraint("raw_text is not null or file_artifact_id is not null or value_payload <> '{}'::jsonb", name=op.f("ck_submission_evidence_submission_evidence_has_payload")),
        sa.CheckConstraint("status in ('submitted', 'processed', 'invalid', 'archived')", name=op.f("ck_submission_evidence_submission_evidence_status")),
        sa.ForeignKeyConstraint(["evidence_extraction_id"], ["evidence_extractions.id"], name=op.f("fk_submission_evidence_evidence_extraction_id_evidence_extractions")),
        sa.ForeignKeyConstraint(["evidence_type_id"], ["evidence_types.id"], name=op.f("fk_submission_evidence_evidence_type_id_evidence_types")),
        sa.ForeignKeyConstraint(["file_artifact_id"], ["file_artifacts.id"], name=op.f("fk_submission_evidence_file_artifact_id_file_artifacts")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_submission_evidence_organization_id_organizations")),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name=op.f("fk_submission_evidence_submission_id_submissions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_evidence")),
    )
    op.create_index("ix_submission_evidence_extraction", "submission_evidence", ["evidence_extraction_id"])
    op.create_index("ix_submission_evidence_file_artifact", "submission_evidence", ["file_artifact_id"])
    op.create_index("ix_submission_evidence_submission", "submission_evidence", ["submission_id"])
    op.create_index("ix_submission_evidence_type", "submission_evidence", ["evidence_type_id"])

    op.create_table(
        "criterion_results",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("grading_result_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_key", sa.String(length=160), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("score", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("max_score", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("confidence is null or (confidence >= 0 and confidence <= 1)", name=op.f("ck_criterion_results_criterion_result_confidence_range")),
        sa.CheckConstraint("source in ('deterministic', 'ai', 'teacher', 'system')", name=op.f("ck_criterion_results_criterion_result_source")),
        sa.ForeignKeyConstraint(["grading_result_id"], ["grading_results.id"], name=op.f("fk_criterion_results_grading_result_id_grading_results")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_criterion_results_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_criterion_results")),
    )
    op.create_index("ix_criterion_results_grading_result", "criterion_results", ["grading_result_id"])

    op.create_table(
        "ai_interactions",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("grading_run_id", sa.Uuid(), nullable=True),
        sa.Column("grading_result_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("output_schema_version", sa.String(length=80), nullable=True),
        sa.Column("validation_status", sa.String(length=40), nullable=False),
        jsonb_column("request_metadata"),
        jsonb_column("response_payload"),
        jsonb_column("provider_metadata"),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("validation_status in ('pending', 'valid', 'invalid', 'failed')", name=op.f("ck_ai_interactions_ai_interaction_validation_status")),
        sa.ForeignKeyConstraint(["grading_result_id"], ["grading_results.id"], name=op.f("fk_ai_interactions_grading_result_id_grading_results")),
        sa.ForeignKeyConstraint(["grading_run_id"], ["grading_runs.id"], name=op.f("fk_ai_interactions_grading_run_id_grading_runs")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_ai_interactions_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_interactions")),
    )
    op.create_index("ix_ai_interactions_grading_run", "ai_interactions", ["grading_run_id"])
    op.create_index("ix_ai_interactions_organization", "ai_interactions", ["organization_id"])
    op.create_index("ix_ai_interactions_validation_status", "ai_interactions", ["validation_status"])

    op.create_table(
        "review_tasks",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("assessment_item_id", sa.Uuid(), nullable=True),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("grading_run_id", sa.Uuid(), nullable=True),
        sa.Column("grading_result_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.String(length=40), nullable=False),
        sa.Column("confidence_band", sa.String(length=40), nullable=True),
        sa.Column("escalation_reason", sa.String(length=160), nullable=False),
        jsonb_column("policy_payload"),
        *timestamps(),
        sa.CheckConstraint("priority in ('low', 'normal', 'high', 'urgent')", name=op.f("ck_review_tasks_review_task_priority")),
        sa.CheckConstraint("status in ('open', 'assigned', 'completed', 'cancelled')", name=op.f("ck_review_tasks_review_task_status")),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], name=op.f("fk_review_tasks_assessment_id_assessments")),
        sa.ForeignKeyConstraint(["assessment_item_id"], ["assessment_items.id"], name=op.f("fk_review_tasks_assessment_item_id_assessment_items")),
        sa.ForeignKeyConstraint(["assigned_reviewer_id"], ["users.id"], name=op.f("fk_review_tasks_assigned_reviewer_id_users")),
        sa.ForeignKeyConstraint(["grading_result_id"], ["grading_results.id"], name=op.f("fk_review_tasks_grading_result_id_grading_results")),
        sa.ForeignKeyConstraint(["grading_run_id"], ["grading_runs.id"], name=op.f("fk_review_tasks_grading_run_id_grading_runs")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_review_tasks_organization_id_organizations")),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name=op.f("fk_review_tasks_submission_id_submissions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_tasks")),
    )
    op.create_index("ix_review_tasks_assessment", "review_tasks", ["assessment_id"])
    op.create_index("ix_review_tasks_confidence_band", "review_tasks", ["confidence_band"])
    op.create_index("ix_review_tasks_created_at", "review_tasks", ["created_at"])
    op.create_index("ix_review_tasks_escalation_reason", "review_tasks", ["escalation_reason"])
    op.create_index("ix_review_tasks_organization_status", "review_tasks", ["organization_id", "status"])
    op.create_index("ix_review_tasks_status_reviewer", "review_tasks", ["status", "assigned_reviewer_id"])

    op.create_table(
        "teacher_reviews",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("grading_result_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("final_score", sa.Numeric(precision=10, scale=4), nullable=True),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("decision in ('approve', 'adjust', 'override', 'return_for_regrade')", name=op.f("ck_teacher_reviews_teacher_review_decision")),
        sa.ForeignKeyConstraint(["grading_result_id"], ["grading_results.id"], name=op.f("fk_teacher_reviews_grading_result_id_grading_results")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_teacher_reviews_organization_id_organizations")),
        sa.ForeignKeyConstraint(["review_task_id"], ["review_tasks.id"], name=op.f("fk_teacher_reviews_review_task_id_review_tasks")),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name=op.f("fk_teacher_reviews_reviewer_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teacher_reviews")),
    )
    op.create_index("ix_teacher_reviews_organization", "teacher_reviews", ["organization_id"])
    op.create_index("ix_teacher_reviews_review_task", "teacher_reviews", ["review_task_id"])
    op.create_index("ix_teacher_reviews_reviewer", "teacher_reviews", ["reviewer_id"])

    op.create_table(
        "teacher_overrides",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("teacher_review_id", sa.Uuid(), nullable=False),
        sa.Column("grading_result_id", sa.Uuid(), nullable=False),
        sa.Column("overridden_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("override_type", sa.String(length=80), nullable=False),
        jsonb_column("previous_payload"),
        jsonb_column("new_payload"),
        sa.Column("reason", sa.Text(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("override_type in ('score', 'feedback', 'criterion_result', 'finalization')", name=op.f("ck_teacher_overrides_teacher_override_type")),
        sa.ForeignKeyConstraint(["grading_result_id"], ["grading_results.id"], name=op.f("fk_teacher_overrides_grading_result_id_grading_results")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_teacher_overrides_organization_id_organizations")),
        sa.ForeignKeyConstraint(["overridden_by_user_id"], ["users.id"], name=op.f("fk_teacher_overrides_overridden_by_user_id_users")),
        sa.ForeignKeyConstraint(["teacher_review_id"], ["teacher_reviews.id"], name=op.f("fk_teacher_overrides_teacher_review_id_teacher_reviews")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teacher_overrides")),
    )
    op.create_index("ix_teacher_overrides_grading_result", "teacher_overrides", ["grading_result_id"])
    op.create_index("ix_teacher_overrides_organization", "teacher_overrides", ["organization_id"])

    op.create_table(
        "audit_events",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("submission_id", sa.Uuid(), nullable=True),
        sa.Column("grading_run_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_source", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("entity_type", sa.String(length=160), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=160), nullable=True),
        sa.Column("job_id", sa.String(length=160), nullable=True),
        jsonb_column("previous_state"),
        jsonb_column("new_state"),
        sa.Column("reason", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_audit_events_actor_user_id_users")),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], name=op.f("fk_audit_events_assessment_id_assessments")),
        sa.ForeignKeyConstraint(["grading_run_id"], ["grading_runs.id"], name=op.f("fk_audit_events_grading_run_id_grading_runs")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_audit_events_organization_id_organizations")),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name=op.f("fk_audit_events_submission_id_submissions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_actor", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_assessment", "audit_events", ["assessment_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])
    op.create_index("ix_audit_events_grading_run", "audit_events", ["grading_run_id"])
    op.create_index("ix_audit_events_organization", "audit_events", ["organization_id"])
    op.create_index("ix_audit_events_submission", "audit_events", ["submission_id"])

    op.create_table(
        "subject_packs",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        jsonb_column("config"),
        sa.Column("status", sa.String(length=40), nullable=False),
        *timestamps(),
        sa.CheckConstraint("status in ('active', 'archived')", name=op.f("ck_subject_packs_subject_pack_status")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_subject_packs_organization_id_organizations")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subject_packs")),
        sa.UniqueConstraint("organization_id", "key", name=op.f("uq_subject_packs_organization_id")),
    )
    op.create_index("ix_subject_packs_organization_status", "subject_packs", ["organization_id", "status"])


def downgrade() -> None:
    for table_name in (
        "subject_packs",
        "audit_events",
        "teacher_overrides",
        "teacher_reviews",
        "review_tasks",
        "ai_interactions",
        "criterion_results",
        "submission_evidence",
        "evidence_extractions",
        "grading_results",
        "grading_runs",
        "submissions",
        "answer_key_materials",
        "answer_key_versions",
        "answer_keys",
        "rubric_versions",
        "rubrics",
        "assessment_materials",
        "file_artifacts",
        "assessment_items",
        "assessments",
        "file_purposes",
        "rubric_types",
        "evidence_types",
        "assessment_types",
        "learners",
        "users",
        "organizations",
    ):
        op.drop_table(table_name)
