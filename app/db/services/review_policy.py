from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, cast
from uuid import UUID

from app.db.models import AuditEvent, CriterionResult, GradingResult, GradingRun, ReviewTask, Submission
from app.db.models.review import TeacherOverride, TeacherReview
from app.db.services.answer_lifecycle import request_regrade


REVIEW_TASK_OPEN = "open"
REVIEW_TASK_ASSIGNED = "assigned"
REVIEW_TASK_COMPLETED = "completed"

GRADING_RESULT_NEEDS_REVIEW = "needs_review"
GRADING_RESULT_FINALIZED = "finalized"
GRADING_RESULT_REVIEWED = "reviewed"
GRADING_RESULT_OVERRIDDEN = "overridden"

TEACHER_REVIEW_APPROVE = "approve"
TEACHER_REVIEW_ADJUST = "adjust"
TEACHER_REVIEW_OVERRIDE = "override"
TEACHER_REVIEW_RETURN_FOR_REGRADE = "return_for_regrade"


class ReviewPolicyError(ValueError):
    """Raised when a teacher review action violates review policy."""


class ReviewPolicySession(Protocol):
    def add(self, record: object) -> None: ...

    def flush(self) -> None: ...


@dataclass(frozen=True)
class ReviewDecisionResult:
    review_task: ReviewTask
    teacher_review: TeacherReview
    grading_result: GradingResult
    teacher_override: TeacherOverride | None = None
    regrade_run: GradingRun | None = None


def approve_review_result(
    db: ReviewPolicySession,
    *,
    review_task: ReviewTask,
    grading_result: GradingResult,
    submission: Submission,
    reviewer_id: UUID,
    reason: str,
    request_id: str | None = None,
) -> ReviewDecisionResult:
    _validate_review_context(review_task=review_task, grading_result=grading_result, submission=submission)
    _require_reason(reason)

    previous_result_state = _grading_result_state(grading_result)
    previous_task_state = _review_task_state(review_task)
    review = _create_teacher_review(
        db,
        review_task=review_task,
        grading_result=grading_result,
        reviewer_id=reviewer_id,
        decision=TEACHER_REVIEW_APPROVE,
        reason=reason,
        metadata_payload={"review_action": "approve_result"},
    )
    _finalize_review_task(review_task)
    grading_result.status = GRADING_RESULT_FINALIZED
    grading_result.result_type = GRADING_RESULT_REVIEWED
    _mark_human_reviewed(grading_result, review=review, action="approve_result", reason=reason)
    _audit_review_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        action="teacher_review.completed",
        actor_user_id=reviewer_id,
        previous_state={"review_task": previous_task_state, "grading_result": previous_result_state},
        new_state={
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "decision": review.decision,
            "review_task": _review_task_state(review_task),
            "grading_result": _grading_result_state(grading_result),
        },
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return ReviewDecisionResult(review_task=review_task, teacher_review=review, grading_result=grading_result)


def finalize_review_result(
    db: ReviewPolicySession,
    *,
    review_task: ReviewTask,
    grading_result: GradingResult,
    submission: Submission,
    reviewer_id: UUID,
    reason: str,
    request_id: str | None = None,
) -> ReviewDecisionResult:
    return approve_review_result(
        db,
        review_task=review_task,
        grading_result=grading_result,
        submission=submission,
        reviewer_id=reviewer_id,
        reason=reason,
        request_id=request_id,
    )


def adjust_review_score(
    db: ReviewPolicySession,
    *,
    review_task: ReviewTask,
    grading_result: GradingResult,
    submission: Submission,
    reviewer_id: UUID,
    final_score: Decimal,
    reason: str,
    request_id: str | None = None,
) -> ReviewDecisionResult:
    _validate_review_context(review_task=review_task, grading_result=grading_result, submission=submission)
    _require_reason(reason)
    _validate_score(final_score, grading_result.max_score)

    previous_result_state = _grading_result_state(grading_result)
    previous_task_state = _review_task_state(review_task)
    review = _create_teacher_review(
        db,
        review_task=review_task,
        grading_result=grading_result,
        reviewer_id=reviewer_id,
        decision=TEACHER_REVIEW_ADJUST,
        reason=reason,
        final_score=final_score,
        metadata_payload={"review_action": "adjust_score"},
    )
    override = _create_teacher_override(
        db,
        review=review,
        grading_result=grading_result,
        reviewer_id=reviewer_id,
        override_type="score",
        previous_payload={"total_score": _decimal_text(grading_result.total_score)},
        new_payload={"total_score": _decimal_text(final_score)},
        reason=reason,
    )
    grading_result.total_score = final_score
    grading_result.status = GRADING_RESULT_FINALIZED
    grading_result.result_type = GRADING_RESULT_OVERRIDDEN
    _finalize_review_task(review_task)
    _mark_human_reviewed(grading_result, review=review, action="adjust_score", reason=reason)
    _audit_review_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        action="teacher_review.completed",
        actor_user_id=reviewer_id,
        previous_state={"review_task": previous_task_state, "grading_result": previous_result_state},
        new_state={
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "decision": review.decision,
            "review_task": _review_task_state(review_task),
            "grading_result": _grading_result_state(grading_result),
        },
        reason=reason,
        request_id=request_id,
    )
    _audit_override_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        review=review,
        override=override,
        actor_user_id=reviewer_id,
        previous_state={"grading_result": previous_result_state},
        new_state={"grading_result": _grading_result_state(grading_result)},
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return ReviewDecisionResult(
        review_task=review_task,
        teacher_review=review,
        grading_result=grading_result,
        teacher_override=override,
    )


def edit_review_feedback(
    db: ReviewPolicySession,
    *,
    review_task: ReviewTask,
    grading_result: GradingResult,
    submission: Submission,
    reviewer_id: UUID,
    feedback: str,
    reason: str,
    request_id: str | None = None,
) -> ReviewDecisionResult:
    _validate_review_context(review_task=review_task, grading_result=grading_result, submission=submission)
    _require_reason(reason)
    if not feedback.strip():
        raise ReviewPolicyError("Edited feedback cannot be blank.")

    previous_result_state = _grading_result_state(grading_result)
    previous_task_state = _review_task_state(review_task)
    review = _create_teacher_review(
        db,
        review_task=review_task,
        grading_result=grading_result,
        reviewer_id=reviewer_id,
        decision=TEACHER_REVIEW_OVERRIDE,
        reason=reason,
        metadata_payload={"review_action": "edit_feedback"},
    )
    override = _create_teacher_override(
        db,
        review=review,
        grading_result=grading_result,
        reviewer_id=reviewer_id,
        override_type="feedback",
        previous_payload={"feedback": grading_result.feedback},
        new_payload={"feedback": feedback},
        reason=reason,
    )
    grading_result.feedback = feedback
    grading_result.status = GRADING_RESULT_FINALIZED
    grading_result.result_type = GRADING_RESULT_OVERRIDDEN
    _finalize_review_task(review_task)
    _mark_human_reviewed(grading_result, review=review, action="edit_feedback", reason=reason)
    _audit_review_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        action="teacher_review.completed",
        actor_user_id=reviewer_id,
        previous_state={"review_task": previous_task_state, "grading_result": previous_result_state},
        new_state={
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "decision": review.decision,
            "review_task": _review_task_state(review_task),
            "grading_result": _grading_result_state(grading_result),
        },
        reason=reason,
        request_id=request_id,
    )
    _audit_override_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        review=review,
        override=override,
        actor_user_id=reviewer_id,
        previous_state={"grading_result": previous_result_state},
        new_state={"grading_result": _grading_result_state(grading_result)},
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return ReviewDecisionResult(
        review_task=review_task,
        teacher_review=review,
        grading_result=grading_result,
        teacher_override=override,
    )


def override_criterion_result(
    db: ReviewPolicySession,
    *,
    review_task: ReviewTask,
    grading_result: GradingResult,
    submission: Submission,
    reviewer_id: UUID,
    criterion_key: str,
    score: Decimal,
    max_score: Decimal | None,
    explanation: str,
    reason: str,
    previous_criterion_result: CriterionResult | None = None,
    metadata_payload: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> ReviewDecisionResult:
    _validate_review_context(review_task=review_task, grading_result=grading_result, submission=submission)
    _require_reason(reason)
    if not criterion_key.strip():
        raise ReviewPolicyError("Criterion override requires a criterion key.")
    if not explanation.strip():
        raise ReviewPolicyError("Criterion override requires an explanation.")
    _validate_score(score, max_score)
    if previous_criterion_result is not None and previous_criterion_result.grading_result_id != grading_result.id:
        raise ReviewPolicyError("Previous criterion result must belong to the reviewed grading result.")

    previous_result_state = _grading_result_state(grading_result)
    previous_task_state = _review_task_state(review_task)
    review = _create_teacher_review(
        db,
        review_task=review_task,
        grading_result=grading_result,
        reviewer_id=reviewer_id,
        decision=TEACHER_REVIEW_OVERRIDE,
        reason=reason,
        metadata_payload={"review_action": "override_criterion_result", "criterion_key": criterion_key},
    )
    previous_payload = (
        _criterion_result_state(previous_criterion_result)
        if previous_criterion_result is not None
        else {"criterion_key": criterion_key, "source": None}
    )
    new_payload = {
        "criterion_key": criterion_key,
        "score": _decimal_text(score),
        "max_score": _decimal_text(max_score),
        "explanation": explanation,
        "metadata_payload": copy.deepcopy(metadata_payload) if metadata_payload is not None else {},
    }
    override = _create_teacher_override(
        db,
        review=review,
        grading_result=grading_result,
        reviewer_id=reviewer_id,
        override_type="criterion_result",
        previous_payload=previous_payload,
        new_payload=new_payload,
        reason=reason,
    )
    criterion = CriterionResult(
        organization_id=submission.organization_id,
        grading_result_id=grading_result.id,
        criterion_key=criterion_key,
        source="teacher",
        score=score,
        max_score=max_score,
        confidence=None,
        explanation=explanation,
        metadata_payload={
            **(copy.deepcopy(metadata_payload) if metadata_payload is not None else {}),
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "teacher_override_id": str(override.id) if override.id is not None else None,
            "previous_criterion_result_id": (
                str(previous_criterion_result.id)
                if previous_criterion_result is not None and previous_criterion_result.id is not None
                else None
            ),
        },
    )
    db.add(criterion)
    grading_result.status = GRADING_RESULT_FINALIZED
    grading_result.result_type = GRADING_RESULT_OVERRIDDEN
    _finalize_review_task(review_task)
    _mark_human_reviewed(grading_result, review=review, action="override_criterion_result", reason=reason)
    _audit_review_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        action="teacher_review.completed",
        actor_user_id=reviewer_id,
        previous_state={"review_task": previous_task_state, "grading_result": previous_result_state},
        new_state={
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "decision": review.decision,
            "review_task": _review_task_state(review_task),
            "grading_result": _grading_result_state(grading_result),
        },
        reason=reason,
        request_id=request_id,
    )
    _audit_override_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        review=review,
        override=override,
        actor_user_id=reviewer_id,
        previous_state={"grading_result": previous_result_state, "criterion_result": previous_payload},
        new_state={"grading_result": _grading_result_state(grading_result), "criterion_result": new_payload},
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return ReviewDecisionResult(
        review_task=review_task,
        teacher_review=review,
        grading_result=grading_result,
        teacher_override=override,
    )


def return_review_for_regrade(
    db: ReviewPolicySession,
    *,
    review_task: ReviewTask,
    grading_result: GradingResult,
    submission: Submission,
    reviewer_id: UUID,
    reason: str,
    request_id: str | None = None,
    context_payload: dict[str, Any] | None = None,
) -> ReviewDecisionResult:
    _validate_review_context(review_task=review_task, grading_result=grading_result, submission=submission)
    _require_reason(reason)

    previous_result_state = _grading_result_state(grading_result)
    previous_task_state = _review_task_state(review_task)
    review = _create_teacher_review(
        db,
        review_task=review_task,
        grading_result=grading_result,
        reviewer_id=reviewer_id,
        decision=TEACHER_REVIEW_RETURN_FOR_REGRADE,
        reason=reason,
        metadata_payload={"review_action": "return_for_regrade"},
    )
    _finalize_review_task(review_task)
    _mark_human_reviewed(grading_result, review=review, action="return_for_regrade", reason=reason)
    regrade_context = copy.deepcopy(context_payload) if context_payload is not None else {}
    regrade_context.update(
        {
            "review_task_id": str(review_task.id) if review_task.id is not None else None,
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "previous_grading_result_id": str(grading_result.id) if grading_result.id is not None else None,
        }
    )
    regrade_run = request_regrade(
        cast(Any, db),
        submission=submission,
        rubric_version_id=grading_result.rubric_version_id,
        answer_key_version_id=grading_result.answer_key_version_id,
        grading_policy_version=grading_result.explanation_payload.get("policy", {}).get("grading_policy_version"),
        triggered_by_user_id=reviewer_id,
        trigger_source="teacher",
        reason=reason,
        request_id=request_id,
        context_payload=regrade_context,
    )
    _audit_review_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        action="teacher_review.returned_for_regrade",
        actor_user_id=reviewer_id,
        previous_state={"review_task": previous_task_state, "grading_result": previous_result_state},
        new_state={
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "review_task": _review_task_state(review_task),
            "regrade_run_id": str(regrade_run.id) if regrade_run.id is not None else None,
        },
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return ReviewDecisionResult(
        review_task=review_task,
        teacher_review=review,
        grading_result=grading_result,
        regrade_run=regrade_run,
    )


def _validate_review_context(
    *,
    review_task: ReviewTask,
    grading_result: GradingResult,
    submission: Submission,
) -> None:
    if review_task.status not in {REVIEW_TASK_OPEN, REVIEW_TASK_ASSIGNED}:
        raise ReviewPolicyError("Review task is not open for teacher action.")
    if (
        review_task.organization_id != submission.organization_id
        or grading_result.organization_id != submission.organization_id
    ):
        raise ReviewPolicyError("Review context must belong to one organization.")
    if review_task.submission_id != submission.id:
        raise ReviewPolicyError("Review task does not belong to the supplied submission.")
    if review_task.grading_result_id is not None and review_task.grading_result_id != grading_result.id:
        raise ReviewPolicyError("Review task does not belong to the supplied grading result.")
    if grading_result.status != GRADING_RESULT_NEEDS_REVIEW:
        raise ReviewPolicyError("Only grading results that need review can be resolved by teacher review.")


def _require_reason(reason: str) -> None:
    if not reason.strip():
        raise ReviewPolicyError("Teacher review decisions require a reason.")


def _validate_score(score: Decimal, max_score: Decimal | None) -> None:
    if score < Decimal("0"):
        raise ReviewPolicyError("Scores cannot be negative.")
    if max_score is not None and score > max_score:
        raise ReviewPolicyError("Scores cannot exceed the maximum score.")


def _create_teacher_review(
    db: ReviewPolicySession,
    *,
    review_task: ReviewTask,
    grading_result: GradingResult,
    reviewer_id: UUID,
    decision: str,
    reason: str,
    final_score: Decimal | None = None,
    metadata_payload: dict[str, Any] | None = None,
) -> TeacherReview:
    review = TeacherReview(
        organization_id=review_task.organization_id,
        review_task_id=review_task.id,
        reviewer_id=reviewer_id,
        grading_result_id=grading_result.id,
        decision=decision,
        comments=reason,
        final_score=final_score,
        metadata_payload=copy.deepcopy(metadata_payload) if metadata_payload is not None else {},
    )
    db.add(review)
    db.flush()
    return review


def _create_teacher_override(
    db: ReviewPolicySession,
    *,
    review: TeacherReview,
    grading_result: GradingResult,
    reviewer_id: UUID,
    override_type: str,
    previous_payload: dict[str, Any],
    new_payload: dict[str, Any],
    reason: str,
) -> TeacherOverride:
    override = TeacherOverride(
        organization_id=review.organization_id,
        teacher_review_id=review.id,
        grading_result_id=grading_result.id,
        overridden_by_user_id=reviewer_id,
        override_type=override_type,
        previous_payload=copy.deepcopy(previous_payload),
        new_payload=copy.deepcopy(new_payload),
        reason=reason,
    )
    db.add(override)
    db.flush()
    return override


def _finalize_review_task(review_task: ReviewTask) -> None:
    review_task.status = REVIEW_TASK_COMPLETED


def _mark_human_reviewed(
    grading_result: GradingResult,
    *,
    review: TeacherReview,
    action: str,
    reason: str,
) -> None:
    payload = copy.deepcopy(grading_result.explanation_payload or {})
    history = list(payload.get("teacher_review_history", []))
    history.append(
        {
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "decision": review.decision,
            "action": action,
            "reason": reason,
        }
    )
    payload["teacher_review_history"] = history
    payload["finalization"] = {
        "source": "teacher_review",
        "teacher_review_id": str(review.id) if review.id is not None else None,
        "decision": review.decision,
    }
    grading_result.explanation_payload = payload


def _audit_override_event(
    db: ReviewPolicySession,
    *,
    submission: Submission,
    review_task: ReviewTask,
    grading_result: GradingResult,
    review: TeacherReview,
    override: TeacherOverride,
    actor_user_id: UUID,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    reason: str,
    request_id: str | None,
) -> None:
    _audit_review_event(
        db,
        submission=submission,
        review_task=review_task,
        grading_result=grading_result,
        action="teacher_override.applied",
        actor_user_id=actor_user_id,
        previous_state=previous_state,
        new_state={
            **copy.deepcopy(new_state),
            "teacher_review_id": str(review.id) if review.id is not None else None,
            "teacher_override_id": str(override.id) if override.id is not None else None,
            "override_type": override.override_type,
            "review_task": _review_task_state(review_task),
        },
        reason=reason,
        request_id=request_id,
    )


def _audit_review_event(
    db: ReviewPolicySession,
    *,
    submission: Submission,
    review_task: ReviewTask,
    grading_result: GradingResult,
    action: str,
    actor_user_id: UUID,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    reason: str,
    request_id: str | None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=submission.organization_id,
        assessment_id=submission.assessment_id,
        submission_id=submission.id,
        grading_run_id=grading_result.grading_run_id,
        actor_user_id=actor_user_id,
        actor_source="teacher",
        action=action,
        entity_type="review_task",
        entity_id=review_task.id,
        request_id=request_id,
        previous_state=copy.deepcopy(previous_state),
        new_state=copy.deepcopy(new_state),
        reason=reason,
    )
    db.add(event)
    return event


def _review_task_state(review_task: ReviewTask) -> dict[str, Any]:
    return {
        "id": str(review_task.id) if review_task.id is not None else None,
        "status": review_task.status,
        "grading_run_id": str(review_task.grading_run_id) if review_task.grading_run_id is not None else None,
        "grading_result_id": str(review_task.grading_result_id) if review_task.grading_result_id is not None else None,
        "escalation_reason": review_task.escalation_reason,
    }


def _grading_result_state(grading_result: GradingResult) -> dict[str, Any]:
    return {
        "id": str(grading_result.id) if grading_result.id is not None else None,
        "status": grading_result.status,
        "result_type": grading_result.result_type,
        "total_score": _decimal_text(grading_result.total_score),
        "max_score": _decimal_text(grading_result.max_score),
        "confidence": _decimal_text(grading_result.confidence),
        "rubric_version_id": (
            str(grading_result.rubric_version_id) if grading_result.rubric_version_id is not None else None
        ),
        "answer_key_version_id": (
            str(grading_result.answer_key_version_id) if grading_result.answer_key_version_id is not None else None
        ),
    }


def _criterion_result_state(criterion_result: CriterionResult) -> dict[str, Any]:
    return {
        "id": str(criterion_result.id) if criterion_result.id is not None else None,
        "criterion_key": criterion_result.criterion_key,
        "source": criterion_result.source,
        "score": _decimal_text(criterion_result.score),
        "max_score": _decimal_text(criterion_result.max_score),
        "confidence": _decimal_text(criterion_result.confidence),
        "explanation": criterion_result.explanation,
        "metadata_payload": copy.deepcopy(criterion_result.metadata_payload),
    }


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
