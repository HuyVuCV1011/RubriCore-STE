"""answer lifecycle

Revision ID: 0006_answer_lifecycle
Revises: 0005_rubric_framework
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0006_answer_lifecycle"
down_revision: str | None = "0005_rubric_framework"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SUBMISSION_STATUS_CHECK = (
    "status in ("
    "'draft', 'submitted', 'superseded', 'withdrawn', 'archived', "
    "'processing', 'graded', 'returned'"
    ")"
)


def upgrade() -> None:
    op.add_column("submissions", sa.Column("supersedes_submission_id", sa.Uuid(), nullable=True))
    op.add_column("submissions", sa.Column("superseded_by_submission_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_submissions_supersedes_submission_id_submissions"),
        "submissions",
        "submissions",
        ["supersedes_submission_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_submissions_superseded_by_submission_id_submissions"),
        "submissions",
        "submissions",
        ["superseded_by_submission_id"],
        ["id"],
    )
    op.create_index("ix_submissions_supersedes", "submissions", ["supersedes_submission_id"])
    op.create_index("ix_submissions_superseded_by", "submissions", ["superseded_by_submission_id"])

    op.drop_constraint(op.f("ck_submissions_submission_status"), "submissions", type_="check")
    op.create_check_constraint(op.f("ck_submissions_submission_status"), "submissions", SUBMISSION_STATUS_CHECK)
    op.create_check_constraint(
        op.f("ck_submissions_submission_superseded_by_requires_status"),
        "submissions",
        "superseded_by_submission_id is null or status = 'superseded'",
    )
    op.alter_column("submissions", "status", server_default="draft")


def downgrade() -> None:
    op.alter_column("submissions", "status", server_default="submitted")
    op.drop_constraint(
        op.f("ck_submissions_submission_superseded_by_requires_status"),
        "submissions",
        type_="check",
    )
    op.drop_constraint(op.f("ck_submissions_submission_status"), "submissions", type_="check")
    op.create_check_constraint(
        op.f("ck_submissions_submission_status"),
        "submissions",
        "status in ('draft', 'submitted', 'processing', 'graded', 'returned', 'archived')",
    )
    op.drop_index("ix_submissions_superseded_by", table_name="submissions")
    op.drop_index("ix_submissions_supersedes", table_name="submissions")
    op.drop_constraint(
        op.f("fk_submissions_superseded_by_submission_id_submissions"),
        "submissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_submissions_supersedes_submission_id_submissions"),
        "submissions",
        type_="foreignkey",
    )
    op.drop_column("submissions", "superseded_by_submission_id")
    op.drop_column("submissions", "supersedes_submission_id")
