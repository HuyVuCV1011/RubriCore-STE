from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy.orm import Session

from app.db.models import (
    AnswerKey,
    AnswerKeyVersion,
    GradingResult,
    GradingRun,
    Rubric,
    RubricVersion,
    Submission,
    TeacherReview,
)
from app.db.services.answer_keys import create_answer_key, publish_answer_key_version, update_answer_key_draft
from app.db.services.calibration import reviewed_example_payload
from app.db.services.grading_orchestration import AIGradingProvider, GradingPolicy, orchestrate_grading_for_submission
from app.db.services.pilot_io import export_grading_result
from app.db.services.review_queue import list_review_tasks, review_task_summary
from app.db.services.rubric_authoring import update_rubric_draft
from app.db.services.subject_packs import create_subject_pack, resolve_active_subject_pack, subject_pack_summary
from app.pilot.contracts import (
    AnswerKeyCreateRequest,
    AnswerKeyPublishRequest,
    AnswerKeyUpdateRequest,
    AnswerKeyVersionResponse,
    AIInteractionSummaryResponse,
    FixtureManifestRequest,
    GradingRunRequest,
    GradingRunResponse,
    GradingResultExportResponse,
    ReviewedExamplePayloadResponse,
    ReviewTaskListRequest,
    ReviewTaskSummaryResponse,
    RubricDraftUpdateRequest,
    SubjectPackCreateRequest,
    SubjectPackSummaryResponse,
)


class PilotWorkflowError(ValueError):
    """Raised when a pilot workflow cannot produce the requested response."""


def create_subject_pack_workflow(db: Session, request: SubjectPackCreateRequest) -> SubjectPackSummaryResponse:
    pack = create_subject_pack(
        db,
        organization_id=request.organization_id,
        key=request.key,
        name=request.name,
        description=request.description,
        config=request.config,
    )
    return SubjectPackSummaryResponse.model_validate(subject_pack_summary(pack))


def resolve_subject_pack_workflow(
    db: Session,
    *,
    key: str,
    organization_id: uuid.UUID | None,
    allow_global: bool = True,
) -> SubjectPackSummaryResponse:
    pack = resolve_active_subject_pack(db, key=key, organization_id=organization_id, allow_global=allow_global)
    if pack is None:
        raise PilotWorkflowError(f"Active subject pack {key!r} was not found.")
    return SubjectPackSummaryResponse.model_validate(subject_pack_summary(pack))


def create_answer_key_workflow(db: Session, request: AnswerKeyCreateRequest) -> AnswerKey:
    return create_answer_key(
        cast(Any, db),
        organization_id=request.organization_id,
        assessment_item_id=request.assessment_item_id,
        title=request.title,
        draft_key=request.draft_key,
        created_by_user_id=request.created_by_user_id,
    )


def update_answer_key_draft_workflow(
    db: Session,
    *,
    answer_key: AnswerKey,
    request: AnswerKeyUpdateRequest,
) -> AnswerKey:
    return update_answer_key_draft(db, answer_key=answer_key, draft_key=request.draft_key)


def publish_answer_key_workflow(
    db: Session,
    *,
    answer_key: AnswerKey,
    request: AnswerKeyPublishRequest,
) -> AnswerKeyVersionResponse:
    version = publish_answer_key_version(
        db,
        answer_key=answer_key,
        published_by_user_id=request.published_by_user_id,
        reason=request.reason,
        request_id=request.request_id,
    )
    return AnswerKeyVersionResponse.model_validate(
        {
            "answer_key_id": str(answer_key.id),
            "answer_key_version_id": str(version.id) if version.id is not None else None,
            "version_number": version.version_number,
            "status": version.status,
        }
    )


def list_review_task_summaries_workflow(
    db: Session,
    request: ReviewTaskListRequest,
) -> list[ReviewTaskSummaryResponse]:
    tasks = list_review_tasks(
        db,
        organization_id=request.organization_id,
        statuses=set(request.statuses) if request.statuses is not None else None,
        assigned_reviewer_id=request.assigned_reviewer_id,
        assessment_id=request.assessment_id,
        assessment_item_id=request.assessment_item_id,
        priority=request.priority,
        confidence_band=request.confidence_band,
        limit=request.limit,
    )
    return [ReviewTaskSummaryResponse.model_validate(review_task_summary(task)) for task in tasks]


def update_rubric_draft_workflow(
    db: Session,
    *,
    rubric: Rubric,
    request: RubricDraftUpdateRequest,
) -> Rubric:
    return update_rubric_draft(
        db,
        rubric=rubric,
        draft_schema=request.draft_schema,
        actor_user_id=request.actor_user_id,
        actor_source=request.actor_source,
        title=request.title,
        description=request.description,
        metadata_patch=request.metadata_patch,
        reason=request.reason,
        request_id=request.request_id,
    )


def validate_fixture_manifest_workflow(request: FixtureManifestRequest) -> list[str]:
    return request.validation_errors()


def run_grading_workflow(
    db: Session,
    *,
    submission: Submission,
    rubric_version: RubricVersion | None,
    answer_key_version: AnswerKeyVersion | None,
    ai_provider: AIGradingProvider | None,
    request: GradingRunRequest,
    actor_user_id: uuid.UUID,
) -> GradingRunResponse:
    policy = GradingPolicy(
        confidence_threshold=request.confidence_threshold,
        review_threshold=request.review_threshold,
        ai_allowed=request.ai_allowed,
        ai_required=request.ai_required,
        auto_finalize_allowed=request.auto_finalize_allowed,
        mandatory_review=request.mandatory_review,
        grading_policy_version="pilot-api-v1",
        prompt_version="pilot-ollama-grading-v1",
        ai_output_schema_version="phase-1-grading-output-v1",
    )
    outcome = orchestrate_grading_for_submission(
        cast(Any, db),
        submission=submission,
        rubric_version=rubric_version,
        answer_key_version=answer_key_version,
        selected_levels_by_criterion=request.selected_levels_by_criterion,
        ai_provider=ai_provider if request.ai_allowed else None,
        answer_key_required=request.answer_key_required,
        policy=policy,
        triggered_by_user_id=actor_user_id,
        trigger_source="pilot_api",
        reason=request.reason,
        request_id=request.request_id,
        context_payload={"api_route": "/pilot/grading-runs"},
    )
    return GradingRunResponse(
        grading_run_id=str(outcome.grading_run.id),
        grading_run_status=outcome.grading_run.status,
        grading_result=export_grading_result_workflow(outcome.grading_result) if outcome.grading_result else None,
        review_task_id=str(outcome.review_task.id) if outcome.review_task is not None else None,
        ai_interaction=(
            AIInteractionSummaryResponse.model_validate(
                {
                    "id": str(outcome.ai_interaction.id) if outcome.ai_interaction.id is not None else None,
                    "provider": outcome.ai_interaction.provider,
                    "model": outcome.ai_interaction.model,
                    "validation_status": outcome.ai_interaction.validation_status,
                    "error_message": outcome.ai_interaction.error_message,
                }
            )
            if outcome.ai_interaction is not None
            else None
        ),
    )


def export_grading_result_workflow(result: GradingResult) -> GradingResultExportResponse:
    return GradingResultExportResponse.model_validate(export_grading_result(result))


def reviewed_example_payload_workflow(
    *,
    result: GradingResult,
    grading_run: GradingRun | None = None,
    teacher_review: TeacherReview | None = None,
) -> ReviewedExamplePayloadResponse:
    return ReviewedExamplePayloadResponse.model_validate(
        reviewed_example_payload(result=result, grading_run=grading_run, teacher_review=teacher_review)
    )
