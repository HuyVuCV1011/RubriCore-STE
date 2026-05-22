import pytest

from app.db.models import AssessmentItem, OutputType
from app.taxonomy import TaxonomyCompatibilityError, validate_taxonomy_combination


def test_output_type_model_is_registered() -> None:
    assert OutputType.__tablename__ == "output_types"
    assert "output_type_id" in AssessmentItem.__table__.columns


def test_accepts_compatible_code_assignment_taxonomy() -> None:
    validate_taxonomy_combination(
        assessment_type="code-assignment",
        evidence_type="code",
        output_type="executable-behavior",
        rubric_type="checklist",
    )


def test_rejects_incompatible_evidence_type() -> None:
    with pytest.raises(TaxonomyCompatibilityError):
        validate_taxonomy_combination(
            assessment_type="numeric-answer",
            evidence_type="image",
        )


def test_rejects_unknown_taxonomy_key() -> None:
    with pytest.raises(TaxonomyCompatibilityError):
        validate_taxonomy_combination(assessment_type="code_assignment")
