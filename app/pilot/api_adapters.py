from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models import GradingResult, GradingRun, TeacherReview
from app.db.services.evaluation import evaluation_dataset_report, json_safe_evaluation_report
from app.db.services.pilot_io import validate_fixture_manifest
from app.pilot.contracts import (
    EvaluationBaselineRequest,
    EvaluationBaselineResponse,
    FixtureManifestRequest,
    FixtureManifestValidationResponse,
    GradingResultExportResponse,
    ReviewedExamplePayloadResponse,
    SubjectPackSummaryResponse,
)
from app.pilot.workflows import (
    export_grading_result_workflow,
    reviewed_example_payload_workflow,
    validate_fixture_manifest_workflow,
)


@dataclass(frozen=True)
class ApiRoutePlan:
    method: str
    path: str
    adapter: str
    purpose: str


PHASE4_SAFE_ROUTE_PLAN: tuple[ApiRoutePlan, ...] = (
    ApiRoutePlan(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        adapter="validate_fixture_manifest_adapter",
        purpose="Validate public-safe fixture manifests before import or evaluation use.",
    ),
    ApiRoutePlan(
        method="POST",
        path="/pilot/evaluation/public-baseline",
        adapter="public_evaluation_baseline_adapter",
        purpose="Produce a public-safe evaluation baseline report from a provided manifest payload.",
    ),
    ApiRoutePlan(
        method="POST",
        path="/pilot/subject-packs/summary",
        adapter="subject_pack_summary_adapter",
        purpose="Normalize an existing subject-pack summary payload into the response contract.",
    ),
    ApiRoutePlan(
        method="GET",
        path="/pilot/grading-results/{grading_result_id}/export",
        adapter="grading_result_export_adapter",
        purpose="Expose the existing grading-result export response shape.",
    ),
    ApiRoutePlan(
        method="GET",
        path="/pilot/grading-results/{grading_result_id}/reviewed-example",
        adapter="reviewed_example_payload_adapter",
        purpose="Expose the existing reviewed-result calibration response shape.",
    ),
)

PHASE4_SERVICE_ONLY_WORKFLOWS: tuple[str, ...] = (
    "provider_calls",
    "prompt_execution",
    "vector_retrieval",
    "rich_file_upload_or_import",
    "private_fixture_loading",
    "production_authentication_or_authorization",
    "teacher_facing_ui",
)


def route_plan() -> tuple[ApiRoutePlan, ...]:
    return PHASE4_SAFE_ROUTE_PLAN


def service_only_workflows() -> tuple[str, ...]:
    return PHASE4_SERVICE_ONLY_WORKFLOWS


def validate_fixture_manifest_adapter(payload: dict[str, Any]) -> FixtureManifestValidationResponse:
    request = FixtureManifestRequest.model_validate(payload)
    return FixtureManifestValidationResponse(validation_errors=validate_fixture_manifest_workflow(request))


def public_evaluation_baseline_adapter(payload: dict[str, Any]) -> EvaluationBaselineResponse:
    request = EvaluationBaselineRequest.model_validate(payload)
    validation_errors = validate_fixture_manifest(request.manifest)
    if validation_errors:
        return EvaluationBaselineResponse(validation_errors=validation_errors)

    report = evaluation_dataset_report(manifest=request.manifest, use_expected_as_actual=True)
    return EvaluationBaselineResponse(
        validation_errors=[],
        report=json_safe_evaluation_report(report),
    )


def subject_pack_summary_adapter(payload: dict[str, Any]) -> SubjectPackSummaryResponse:
    return SubjectPackSummaryResponse.model_validate(payload)


def grading_result_export_adapter(result: GradingResult) -> GradingResultExportResponse:
    return export_grading_result_workflow(result)


def reviewed_example_payload_adapter(
    *,
    result: GradingResult,
    grading_run: GradingRun | None = None,
    teacher_review: TeacherReview | None = None,
) -> ReviewedExamplePayloadResponse:
    return reviewed_example_payload_workflow(
        result=result,
        grading_run=grading_run,
        teacher_review=teacher_review,
    )
