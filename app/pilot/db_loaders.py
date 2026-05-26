from __future__ import annotations

from sqlalchemy.orm import Session

import uuid

from app.db.models import (
    AnswerKeyVersion,
    CriterionResult,
    GradingResult,
    ReviewTask,
    RubricVersion,
    SubjectPack,
    Submission,
)
from app.db.services.subject_packs import resolve_active_subject_pack
from app.pilot.authz import (
    PilotAuthContext,
    PilotPermission,
    TenantScopedResource,
    authorize_tenant_resource,
    require_permission,
)


def load_subject_pack_for_context(
    db: Session,
    *,
    key: str,
    context: PilotAuthContext,
    allow_global: bool = True,
) -> SubjectPack | None:
    require_permission(context, PilotPermission.READ_SUBJECT_PACKS)
    pack = resolve_active_subject_pack(
        db,
        key=key,
        organization_id=context.organization_id,
        allow_global=allow_global,
    )
    if pack is None:
        return None
    if pack.organization_id is None:
        return pack

    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=pack.organization_id,
            resource_type="subject_pack",
            resource_id=pack.id,
        ),
        permission=PilotPermission.READ_SUBJECT_PACKS,
    )
    return pack


def load_submission_for_grading_context(
    db: Session,
    *,
    submission_id: uuid.UUID,
    context: PilotAuthContext,
) -> Submission | None:
    require_permission(context, PilotPermission.RUN_GRADING)
    submission = db.get(Submission, submission_id)
    if submission is None:
        return None
    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=submission.organization_id,
            resource_type="submission",
            resource_id=submission.id,
        ),
        permission=PilotPermission.RUN_GRADING,
    )
    return submission


def load_rubric_version_for_grading_context(
    db: Session,
    *,
    rubric_version_id: uuid.UUID | None,
    context: PilotAuthContext,
) -> RubricVersion | None:
    if rubric_version_id is None:
        return None
    require_permission(context, PilotPermission.RUN_GRADING)
    rubric_version = db.get(RubricVersion, rubric_version_id)
    if rubric_version is None:
        return None
    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=rubric_version.organization_id,
            resource_type="rubric_version",
            resource_id=rubric_version.id,
        ),
        permission=PilotPermission.RUN_GRADING,
    )
    return rubric_version


def load_answer_key_version_for_grading_context(
    db: Session,
    *,
    answer_key_version_id: uuid.UUID | None,
    context: PilotAuthContext,
) -> AnswerKeyVersion | None:
    if answer_key_version_id is None:
        return None
    require_permission(context, PilotPermission.RUN_GRADING)
    answer_key_version = db.get(AnswerKeyVersion, answer_key_version_id)
    if answer_key_version is None:
        return None
    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=answer_key_version.organization_id,
            resource_type="answer_key_version",
            resource_id=answer_key_version.id,
        ),
        permission=PilotPermission.RUN_GRADING,
    )
    return answer_key_version


def load_review_task_for_action_context(
    db: Session,
    *,
    review_task_id: uuid.UUID,
    context: PilotAuthContext,
) -> ReviewTask | None:
    require_permission(context, PilotPermission.WRITE_REVIEW_ACTIONS)
    review_task = db.get(ReviewTask, review_task_id)
    if review_task is None:
        return None
    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=review_task.organization_id,
            resource_type="review_task",
            resource_id=review_task.id,
        ),
        permission=PilotPermission.WRITE_REVIEW_ACTIONS,
    )
    return review_task


def load_grading_result_for_review_action_context(
    db: Session,
    *,
    grading_result_id: uuid.UUID,
    context: PilotAuthContext,
) -> GradingResult | None:
    require_permission(context, PilotPermission.WRITE_REVIEW_ACTIONS)
    grading_result = db.get(GradingResult, grading_result_id)
    if grading_result is None:
        return None
    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=grading_result.organization_id,
            resource_type="grading_result",
            resource_id=grading_result.id,
        ),
        permission=PilotPermission.WRITE_REVIEW_ACTIONS,
    )
    return grading_result


def load_submission_for_review_action_context(
    db: Session,
    *,
    submission_id: uuid.UUID,
    context: PilotAuthContext,
) -> Submission | None:
    require_permission(context, PilotPermission.WRITE_REVIEW_ACTIONS)
    submission = db.get(Submission, submission_id)
    if submission is None:
        return None
    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=submission.organization_id,
            resource_type="submission",
            resource_id=submission.id,
        ),
        permission=PilotPermission.WRITE_REVIEW_ACTIONS,
    )
    return submission


def load_criterion_result_for_review_action_context(
    db: Session,
    *,
    criterion_result_id: uuid.UUID | None,
    context: PilotAuthContext,
) -> CriterionResult | None:
    if criterion_result_id is None:
        return None
    require_permission(context, PilotPermission.WRITE_REVIEW_ACTIONS)
    criterion_result = db.get(CriterionResult, criterion_result_id)
    if criterion_result is None:
        return None
    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=criterion_result.organization_id,
            resource_type="criterion_result",
            resource_id=criterion_result.id,
        ),
        permission=PilotPermission.WRITE_REVIEW_ACTIONS,
    )
    return criterion_result
