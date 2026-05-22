"""rubric framework

Revision ID: 0005_rubric_framework
Revises: 0004_artifact_provenance
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision: str = "0005_rubric_framework"
down_revision: str | None = "0004_artifact_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def jsonb_column(name: str, nullable: bool = False, server_default: str | None = None) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=nullable,
        server_default=sa.text(server_default) if server_default is not None else None,
    )


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), nullable=False)


def upgrade() -> None:
    op.add_column("rubrics", sa.Column("slug", sa.String(length=160), nullable=True))
    op.add_column("rubrics", jsonb_column("metadata_payload", server_default="'{}'::jsonb"))
    op.add_column("rubric_versions", jsonb_column("source_metadata", server_default="'{}'::jsonb"))

    op.create_unique_constraint("uq_rubrics_organization_slug", "rubrics", ["organization_id", "slug"])
    op.create_index("ix_rubrics_organization_slug", "rubrics", ["organization_id", "slug"])
    op.alter_column("rubrics", "metadata_payload", server_default=None)
    op.alter_column("rubric_versions", "source_metadata", server_default=None)

    op.create_table(
        "rubric_criteria",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        jsonb_column("evaluation_hints"),
        *timestamps(),
        sa.CheckConstraint("weight is null or weight > 0", name=op.f("ck_rubric_criteria_rubric_criterion_weight_positive")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_rubric_criteria_organization_id_organizations")),
        sa.ForeignKeyConstraint(["rubric_version_id"], ["rubric_versions.id"], name=op.f("fk_rubric_criteria_rubric_version_id_rubric_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_criteria")),
        sa.UniqueConstraint("rubric_version_id", "key", name="uq_rubric_criteria_version_key"),
        sa.UniqueConstraint("rubric_version_id", "position", name="uq_rubric_criteria_version_position"),
    )
    op.create_index("ix_rubric_criteria_organization", "rubric_criteria", ["organization_id"])
    op.create_index("ix_rubric_criteria_version_position", "rubric_criteria", ["rubric_version_id", "position"])

    op.create_table(
        "performance_levels",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint("score >= 0", name=op.f("ck_performance_levels_performance_level_score_nonnegative")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_performance_levels_organization_id_organizations")),
        sa.ForeignKeyConstraint(["rubric_version_id"], ["rubric_versions.id"], name=op.f("fk_performance_levels_rubric_version_id_rubric_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_performance_levels")),
        sa.UniqueConstraint("rubric_version_id", "key", name="uq_performance_levels_version_key"),
        sa.UniqueConstraint("rubric_version_id", "position", name="uq_performance_levels_version_position"),
    )
    op.create_index("ix_performance_levels_organization", "performance_levels", ["organization_id"])
    op.create_index("ix_performance_levels_version_position", "performance_levels", ["rubric_version_id", "position"])

    op.create_table(
        "rubric_descriptors",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), nullable=False),
        sa.Column("performance_level_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_key", sa.String(length=160), nullable=False),
        sa.Column("performance_level_key", sa.String(length=160), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        jsonb_column("evaluation_hints"),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.ForeignKeyConstraint(["criterion_id"], ["rubric_criteria.id"], name=op.f("fk_rubric_descriptors_criterion_id_rubric_criteria")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_rubric_descriptors_organization_id_organizations")),
        sa.ForeignKeyConstraint(
            ["performance_level_id"],
            ["performance_levels.id"],
            name=op.f("fk_rubric_descriptors_performance_level_id_performance_levels"),
        ),
        sa.ForeignKeyConstraint(["rubric_version_id"], ["rubric_versions.id"], name=op.f("fk_rubric_descriptors_rubric_version_id_rubric_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_descriptors")),
        sa.UniqueConstraint("criterion_id", "performance_level_id", name="uq_rubric_descriptors_criterion_level"),
        sa.UniqueConstraint(
            "rubric_version_id",
            "criterion_key",
            "performance_level_key",
            name="uq_rubric_descriptors_version_keys",
        ),
    )
    op.create_index("ix_rubric_descriptors_criterion", "rubric_descriptors", ["criterion_id"])
    op.create_index("ix_rubric_descriptors_level", "rubric_descriptors", ["performance_level_id"])
    op.create_index("ix_rubric_descriptors_version", "rubric_descriptors", ["rubric_version_id"])

    op.create_table(
        "rubric_bindings",
        uuid_pk(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("assessment_item_id", sa.Uuid(), nullable=True),
        sa.Column("external_context_key", sa.String(length=255), nullable=True),
        sa.Column("context_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("bound_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        jsonb_column("metadata_payload"),
        *timestamps(),
        sa.CheckConstraint(
            "assessment_id is not null or assessment_item_id is not null or external_context_key is not null",
            name=op.f("ck_rubric_bindings_rubric_binding_has_context"),
        ),
        sa.CheckConstraint(
            "context_type in ('assessment', 'assessment_item', 'evaluation_context')",
            name=op.f("ck_rubric_bindings_rubric_binding_context_type"),
        ),
        sa.CheckConstraint(
            "source in ('teacher', 'system', 'fixture_import', 'api_import')",
            name=op.f("ck_rubric_bindings_rubric_binding_source"),
        ),
        sa.CheckConstraint(
            "status in ('active', 'superseded', 'archived')",
            name=op.f("ck_rubric_bindings_rubric_binding_status"),
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], name=op.f("fk_rubric_bindings_assessment_id_assessments")),
        sa.ForeignKeyConstraint(
            ["assessment_item_id"],
            ["assessment_items.id"],
            name=op.f("fk_rubric_bindings_assessment_item_id_assessment_items"),
        ),
        sa.ForeignKeyConstraint(["bound_by_user_id"], ["users.id"], name=op.f("fk_rubric_bindings_bound_by_user_id_users")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_rubric_bindings_organization_id_organizations")),
        sa.ForeignKeyConstraint(["rubric_version_id"], ["rubric_versions.id"], name=op.f("fk_rubric_bindings_rubric_version_id_rubric_versions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_bindings")),
    )
    op.create_index("ix_rubric_bindings_assessment", "rubric_bindings", ["assessment_id"])
    op.create_index("ix_rubric_bindings_assessment_item", "rubric_bindings", ["assessment_item_id"])
    op.create_index("ix_rubric_bindings_external_context", "rubric_bindings", ["external_context_key"])
    op.create_index("ix_rubric_bindings_organization_status", "rubric_bindings", ["organization_id", "status"])
    op.create_index("ix_rubric_bindings_rubric_version", "rubric_bindings", ["rubric_version_id"])


def downgrade() -> None:
    op.drop_index("ix_rubric_bindings_rubric_version", table_name="rubric_bindings")
    op.drop_index("ix_rubric_bindings_organization_status", table_name="rubric_bindings")
    op.drop_index("ix_rubric_bindings_external_context", table_name="rubric_bindings")
    op.drop_index("ix_rubric_bindings_assessment_item", table_name="rubric_bindings")
    op.drop_index("ix_rubric_bindings_assessment", table_name="rubric_bindings")
    op.drop_table("rubric_bindings")

    op.drop_index("ix_rubric_descriptors_version", table_name="rubric_descriptors")
    op.drop_index("ix_rubric_descriptors_level", table_name="rubric_descriptors")
    op.drop_index("ix_rubric_descriptors_criterion", table_name="rubric_descriptors")
    op.drop_table("rubric_descriptors")

    op.drop_index("ix_performance_levels_version_position", table_name="performance_levels")
    op.drop_index("ix_performance_levels_organization", table_name="performance_levels")
    op.drop_table("performance_levels")

    op.drop_index("ix_rubric_criteria_version_position", table_name="rubric_criteria")
    op.drop_index("ix_rubric_criteria_organization", table_name="rubric_criteria")
    op.drop_table("rubric_criteria")

    op.drop_index("ix_rubrics_organization_slug", table_name="rubrics")
    op.drop_constraint("uq_rubrics_organization_slug", "rubrics", type_="unique")
    op.drop_column("rubric_versions", "source_metadata")
    op.drop_column("rubrics", "metadata_payload")
    op.drop_column("rubrics", "slug")
