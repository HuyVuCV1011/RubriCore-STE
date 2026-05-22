from app.db.models import FileArtifact, SubmissionEvidence
from app.db.models.file_artifact import ARTIFACT_SOURCE_FORMAT_CHECK, ARTIFACT_SOURCE_TYPE_CHECK
from sqlalchemy import CheckConstraint


def test_file_artifact_provenance_columns_are_registered() -> None:
    columns = FileArtifact.__table__.columns

    assert "owner_user_id" in columns
    assert columns["owner_user_id"].nullable is True
    assert "uploaded_by_user_id" in columns
    assert columns["uploaded_by_user_id"].nullable is True
    assert columns["source_type"].nullable is False
    assert columns["source_type"].default.arg == "unknown"
    assert columns["source_format"].nullable is False
    assert columns["source_format"].default.arg == "unknown"
    assert columns["uploaded_at"].nullable is False
    assert columns["uploaded_at"].server_default is not None


def test_file_artifact_provenance_values_are_controlled() -> None:
    constraint_sql = {
        str(constraint.sqltext)
        for constraint in FileArtifact.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name
    }

    assert ARTIFACT_SOURCE_TYPE_CHECK in constraint_sql
    assert ARTIFACT_SOURCE_FORMAT_CHECK in constraint_sql


def test_submission_evidence_exposes_file_artifact_link() -> None:
    relationship = SubmissionEvidence.file_artifact.property

    assert relationship.mapper.class_ is FileArtifact
    assert relationship.local_columns == {SubmissionEvidence.__table__.columns["file_artifact_id"]}
