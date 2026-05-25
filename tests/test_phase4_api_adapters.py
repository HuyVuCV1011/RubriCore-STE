import json
import uuid
from decimal import Decimal
from pathlib import Path

from app.db.models import GradingResult
from app.db.services.evaluation import evaluation_dataset_report, json_safe_evaluation_report
from app.pilot import api_adapters
from app.pilot.contracts import FixtureManifestRequest, GradingResultExportResponse


PUBLIC_EVALUATION_MANIFEST = (
    Path(__file__).parent / "fixtures/public/python_score_summary/evaluation_cases/manifest.json"
)


def load_public_evaluation_manifest() -> dict:
    return json.loads(PUBLIC_EVALUATION_MANIFEST.read_text(encoding="utf-8"))


def fixture_manifest_payload() -> dict:
    return {
        "fixture_set": "python-score-summary",
        "title": "Python Score Summary",
        "privacy": "public_safe",
        "files": [
            {
                "path": "assessment_materials/problem_statement.md",
                "purpose": "assessment_material",
                "description": "Synthetic public assignment prompt.",
            }
        ],
    }


def test_route_plan_names_only_safe_phase4_workflows() -> None:
    planned_paths = {route.path for route in api_adapters.route_plan()}

    assert "/pilot/fixtures/manifest/validate" in planned_paths
    assert "/pilot/evaluation/public-baseline" in planned_paths
    assert "provider_calls" in api_adapters.service_only_workflows()
    assert "private_fixture_loading" in api_adapters.service_only_workflows()
    assert all("provider" not in route.path for route in api_adapters.route_plan())
    assert all("private" not in route.path for route in api_adapters.route_plan())


def test_fixture_manifest_adapter_is_thin_contract_and_workflow_wrapper(monkeypatch) -> None:
    calls: list[FixtureManifestRequest] = []

    def fake_validate_fixture_manifest_workflow(request: FixtureManifestRequest) -> list[str]:
        calls.append(request)
        return ["from workflow"]

    monkeypatch.setattr(
        api_adapters,
        "validate_fixture_manifest_workflow",
        fake_validate_fixture_manifest_workflow,
    )

    response = api_adapters.validate_fixture_manifest_adapter(fixture_manifest_payload())

    assert response.validation_errors == ["from workflow"]
    assert len(calls) == 1
    assert calls[0].fixture_set == "python-score-summary"


def test_fixture_manifest_adapter_rejects_sensitive_public_markers() -> None:
    payload = fixture_manifest_payload()
    payload["files"][0]["description"] = "Contains private_prompt material."

    response = api_adapters.validate_fixture_manifest_adapter(payload)

    assert any("sensitive marker" in error for error in response.validation_errors)


def test_public_evaluation_baseline_adapter_matches_service_report_without_private_files() -> None:
    manifest = load_public_evaluation_manifest()

    response = api_adapters.public_evaluation_baseline_adapter({"manifest": manifest})
    expected_report = json_safe_evaluation_report(
        evaluation_dataset_report(manifest=manifest, use_expected_as_actual=True)
    )

    assert response.validation_errors == []
    assert response.report == expected_report
    assert response.report is not None
    assert response.report["passed_count"] == 2
    assert "/fixtures/public/" in PUBLIC_EVALUATION_MANIFEST.as_posix()


def test_public_evaluation_baseline_adapter_rejects_private_markers() -> None:
    manifest = load_public_evaluation_manifest()
    manifest["source_references"][0]["description"] = "Confidential private_school source."

    response = api_adapters.public_evaluation_baseline_adapter({"manifest": manifest})

    assert response.report is None
    assert any("sensitive marker" in error for error in response.validation_errors)


def test_grading_result_export_adapter_returns_existing_contract(monkeypatch) -> None:
    result = GradingResult(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        grading_run_id=uuid.uuid4(),
        result_type="final",
        status="finalized",
        total_score=Decimal("4"),
        max_score=Decimal("5"),
        confidence=Decimal("0.9000"),
        feedback="Synthetic feedback.",
        explanation_payload={"source": "phase4_test"},
    )

    def fake_export_grading_result_workflow(_: GradingResult) -> GradingResultExportResponse:
        return GradingResultExportResponse.model_validate(
            {
                "grading_result_id": str(result.id),
                "grading_run_id": str(result.grading_run_id),
                "rubric_version_id": None,
                "answer_key_version_id": None,
                "result_type": "final",
                "status": "finalized",
                "total_score": "4",
                "max_score": "5",
                "confidence": "0.9000",
                "feedback": "Synthetic feedback.",
                "explanation_payload": {"source": "workflow"},
            }
        )

    monkeypatch.setattr(api_adapters, "export_grading_result_workflow", fake_export_grading_result_workflow)

    response = api_adapters.grading_result_export_adapter(result)

    assert response.total_score == Decimal("4")
    assert response.explanation_payload == {"source": "workflow"}
