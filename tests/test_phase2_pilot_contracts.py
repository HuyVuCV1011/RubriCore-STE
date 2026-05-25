import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.db.models import GradingResult, ReviewTask, SubjectPack
from app.db.services.pilot_io import export_grading_result
from app.db.services.review_queue import review_task_summary
from app.db.services.subject_packs import subject_pack_summary
from app.pilot.contracts import (
    FixtureManifestRequest,
    GradingResultExportResponse,
    ReviewTaskListRequest,
    ReviewTaskSummaryResponse,
    SubjectPackCreateRequest,
    SubjectPackSummaryResponse,
)


def subject_pack_config() -> dict:
    return {
        "schema_version": "1.0",
        "assessment_types": ["code-assignment"],
        "evidence_types": ["code"],
        "output_types": ["executable-behavior"],
        "rubric_types": ["analytic-rubric"],
    }


def test_subject_pack_contracts_match_service_summary() -> None:
    organization_id = uuid.uuid4()
    request = SubjectPackCreateRequest(
        organization_id=organization_id,
        key="python-pilot",
        name="Python Pilot",
        config=subject_pack_config(),
    )
    pack = SubjectPack(
        id=uuid.uuid4(),
        organization_id=request.organization_id,
        key=request.key,
        name=request.name,
        schema_version=request.config["schema_version"],
        config=request.config,
        status="active",
    )

    response = SubjectPackSummaryResponse.model_validate(subject_pack_summary(pack))

    assert response.organization_id == str(organization_id)
    assert response.assessment_types == ["code-assignment"]


def test_review_task_contracts_validate_filters_and_service_summary() -> None:
    organization_id = uuid.uuid4()
    filters = ReviewTaskListRequest(
        organization_id=organization_id,
        statuses={"open", "assigned"},
        priority="urgent",
        limit=25,
    )
    task = ReviewTask(
        id=uuid.uuid4(),
        organization_id=organization_id,
        submission_id=uuid.uuid4(),
        status="open",
        priority=filters.priority,
        escalation_reason="low_confidence",
        policy_payload={"source": "unit_test"},
    )

    response = ReviewTaskSummaryResponse.model_validate(review_task_summary(task))

    assert response.organization_id == str(organization_id)
    assert response.priority == "urgent"
    with pytest.raises(ValidationError):
        ReviewTaskListRequest.model_validate({"organization_id": str(organization_id), "priority": "immediate"})
    with pytest.raises(ValidationError):
        ReviewTaskListRequest.model_validate({"organization_id": str(organization_id), "limit": 0})


def test_fixture_manifest_contract_preserves_public_safe_validation() -> None:
    manifest = FixtureManifestRequest.model_validate(
        {
            "fixture_set": "python-score-summary",
            "title": "Python Score Summary",
            "privacy": "public_safe",
            "files": [
                {
                    "path": "assessment_materials/problem.md",
                    "purpose": "assessment_material",
                    "description": "Problem statement.",
                }
            ],
        }
    )

    assert manifest.validation_errors() == []
    with pytest.raises(ValidationError):
        FixtureManifestRequest.model_validate(
            {
                "fixture_set": "private-demo",
                "title": "Private Demo",
                "privacy": "private",
                "files": [
                    {
                        "path": "assessment_materials/problem.md",
                        "purpose": "assessment_material",
                        "description": "Problem statement.",
                    }
                ],
            }
        )


def test_grading_result_export_contract_accepts_service_payload() -> None:
    result = GradingResult(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        grading_run_id=uuid.uuid4(),
        result_type="final",
        status="finalized",
        total_score=Decimal("4"),
        max_score=Decimal("5"),
        confidence=Decimal("0.9000"),
        feedback="Good work.",
        explanation_payload={"source": "unit_test"},
    )

    response = GradingResultExportResponse.model_validate(export_grading_result(result))

    assert response.total_score == Decimal("4")
    assert response.confidence == Decimal("0.9000")
    assert response.explanation_payload == {"source": "unit_test"}
