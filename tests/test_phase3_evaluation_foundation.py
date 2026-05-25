import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.db.models import CriterionResult, GradingResult, GradingRun, TeacherReview
from app.db.services.calibration import reviewed_result_evaluation_case_payload
from app.db.services.evaluation import (
    criterion_score_agreement,
    evaluation_case_report,
    evaluation_dataset_report,
    final_review_routing_agreement,
    json_safe_evaluation_report,
    total_score_delta,
)
from app.db.services.pilot_io import validate_fixture_manifest


PUBLIC_EVALUATION_MANIFEST = (
    Path(__file__).parent / "fixtures/public/python_score_summary/evaluation_cases/manifest.json"
)


def load_public_evaluation_manifest() -> dict:
    return json.loads(PUBLIC_EVALUATION_MANIFEST.read_text(encoding="utf-8"))


def test_public_evaluation_manifest_declares_public_safe_privacy() -> None:
    manifest = load_public_evaluation_manifest()

    assert manifest["privacy"] == "public_safe"
    assert validate_fixture_manifest(manifest) == []
    assert all(case["metadata"]["privacy"] == "public_safe" for case in manifest["cases"])


def test_public_evaluation_manifest_rejects_escaping_paths() -> None:
    manifest = load_public_evaluation_manifest()
    manifest["files"][0]["path"] = "../private/evaluation_cases.json"

    errors = validate_fixture_manifest(manifest)

    assert any("path must be relative and stay inside fixture root" in error for error in errors)


def test_public_evaluation_manifest_rejects_sensitive_markers() -> None:
    manifest = load_public_evaluation_manifest()
    manifest["source_references"][0]["description"] = "Confidential private_school source."

    errors = validate_fixture_manifest(manifest)

    assert any("sensitive marker" in error for error in errors)


def test_evaluation_metric_helpers_compare_synthetic_payloads() -> None:
    expected = {
        "total_score": "4",
        "routing": "review",
        "criteria": [
            {"criterion_key": "functions", "score": "2"},
            {"criterion_key": "edge_cases", "score": "0"},
            {"criterion_key": "report_shape", "score": "2"},
        ],
    }
    actual = {
        "total_score": Decimal("5"),
        "status": "needs_review",
        "criterion_results": [
            {"criterion_key": "functions", "score": Decimal("2")},
            {"criterion_key": "edge_cases", "score": Decimal("1")},
            {"criterion_key": "report_shape", "score": Decimal("2")},
        ],
    }

    criterion_metrics = criterion_score_agreement(expected, actual)

    assert total_score_delta(expected, actual) == Decimal("1")
    assert criterion_metrics["matching_count"] == 2
    assert criterion_metrics["compared_count"] == 3
    assert criterion_metrics["agreement_rate"] == Decimal("0.6666666666666666666666666667")
    assert criterion_metrics["score_deltas"] == {"edge_cases": Decimal("1")}
    assert final_review_routing_agreement(expected, actual) == {
        "expected_route": "review",
        "actual_route": "review",
        "agrees": True,
    }


def test_evaluation_case_report_and_dataset_report() -> None:
    manifest = load_public_evaluation_manifest()
    actual_outcomes = {
        case["case_id"]: case["expected_outcome"]
        for case in manifest["cases"]
    }
    actual_outcomes["eval_public_safe_002"] = {
        **actual_outcomes["eval_public_safe_002"],
        "total_score": "5",
    }

    report = evaluation_dataset_report(
        manifest=manifest,
        actual_outcomes_by_case_id=actual_outcomes,
    )
    failed_case = next(item for item in report["case_reports"] if item["case_id"] == "eval_public_safe_002")

    assert report["case_count"] == 2
    assert report["evaluated_count"] == 2
    assert report["passed_count"] == 1
    assert report["failed_count"] == 1
    assert failed_case["metrics"]["total_score_delta"] == Decimal("1")
    assert json_safe_evaluation_report(failed_case)["metrics"]["total_score_delta"] == "1"

    single_case = evaluation_case_report(
        case=manifest["cases"][0],
        actual_outcome=manifest["cases"][0]["expected_outcome"],
    )
    assert single_case["passed"] is True


def test_evaluation_dataset_report_tracks_missing_actuals() -> None:
    manifest = load_public_evaluation_manifest()

    report = evaluation_dataset_report(
        manifest=manifest,
        actual_outcomes_by_case_id={"eval_public_safe_001": manifest["cases"][0]["expected_outcome"]},
    )

    assert report["evaluated_count"] == 1
    assert report["missing_actuals"] == ["eval_public_safe_002"]


def test_public_evaluation_manifest_baseline_report_passes() -> None:
    manifest = load_public_evaluation_manifest()

    report = evaluation_dataset_report(manifest=manifest, use_expected_as_actual=True)

    assert report["evaluated_count"] == 2
    assert report["passed_count"] == 2
    assert report["failed_count"] == 0
    assert report["missing_actuals"] == []


def test_reviewed_result_exports_to_evaluation_comparison_shape() -> None:
    organization_id = uuid.uuid4()
    run = GradingRun(
        id=uuid.uuid4(),
        organization_id=organization_id,
        submission_id=uuid.uuid4(),
        status="completed",
        context_payload={},
    )
    result = GradingResult(
        id=uuid.uuid4(),
        organization_id=organization_id,
        grading_run_id=run.id,
        result_type="reviewed",
        status="finalized",
        total_score=Decimal("4"),
        max_score=Decimal("6"),
        confidence=Decimal("0.7200"),
        feedback="Synthetic reviewed feedback.",
        explanation_payload={"source": "unit_test"},
    )
    criteria = [
        CriterionResult(
            organization_id=organization_id,
            grading_result_id=result.id,
            criterion_key="functions",
            source="teacher",
            score=Decimal("2"),
            max_score=Decimal("2"),
            metadata_payload={},
        ),
        CriterionResult(
            organization_id=organization_id,
            grading_result_id=result.id,
            criterion_key="edge_cases",
            source="teacher",
            score=Decimal("0"),
            max_score=Decimal("2"),
            metadata_payload={},
        ),
    ]
    review = TeacherReview(
        id=uuid.uuid4(),
        organization_id=organization_id,
        review_task_id=uuid.uuid4(),
        reviewer_id=uuid.uuid4(),
        grading_result_id=result.id,
        decision="approve",
        metadata_payload={},
    )

    payload = reviewed_result_evaluation_case_payload(
        result=result,
        grading_run=run,
        teacher_review=review,
        criterion_results=criteria,
        case_id="synthetic_reviewed_case",
    )

    assert payload["case_id"] == "synthetic_reviewed_case"
    assert payload["metadata"]["privacy"] == "public_safe"
    assert payload["metadata"]["calibration_source"] == "reviewed_result"
    assert payload["expected_outcome"] == {
        "total_score": "4",
        "max_score": "6",
        "routing": "review",
        "criteria": [
            {"criterion_key": "functions", "score": "2", "max_score": "2"},
            {"criterion_key": "edge_cases", "score": "0", "max_score": "2"},
        ],
    }
    assert total_score_delta(payload["expected_outcome"], {"total_score": "5"}) == Decimal("1")
    assert final_review_routing_agreement(payload["expected_outcome"], {"status": "needs_review"})["agrees"] is True


def test_reviewed_result_evaluation_export_rejects_non_reviewed_results() -> None:
    result = GradingResult(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        grading_run_id=uuid.uuid4(),
        result_type="final",
        status="finalized",
        total_score=Decimal("6"),
        max_score=Decimal("6"),
        explanation_payload={},
    )

    with pytest.raises(ValueError, match="reviewed/overridden"):
        reviewed_result_evaluation_case_payload(result=result, criterion_results=[])
