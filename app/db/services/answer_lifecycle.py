from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select

from app.db.models import AuditEvent, GradingResult, GradingRun, Submission, SubmissionEvidence


SUBMISSION_DRAFT = "draft"
SUBMISSION_SUBMITTED = "submitted"
SUBMISSION_SUPERSEDED = "superseded"
SUBMISSION_WITHDRAWN = "withdrawn"
SUBMISSION_ARCHIVED = "archived"

SUBMISSION_COMPATIBILITY_STATUSES = frozenset({"processing", "graded", "returned"})
SUBMISSION_PACKAGE_STATUSES = frozenset(
    {
        SUBMISSION_DRAFT,
        SUBMISSION_SUBMITTED,
        SUBMISSION_SUPERSEDED,
        SUBMISSION_WITHDRAWN,
        SUBMISSION_ARCHIVED,
    }
)
SUBMISSION_STATUSES = SUBMISSION_PACKAGE_STATUSES | SUBMISSION_COMPATIBILITY_STATUSES

GRADING_RESULT_SUPERSEDED = "superseded"


class AnswerLifecycleError(ValueError):
    """Raised when an answer package lifecycle operation is invalid."""


class SubmissionImmutableError(AnswerLifecycleError):
    """Raised when code attempts to mutate submitted answer content in place."""


class SubmissionIntakeError(AnswerLifecycleError):
    """Raised when a submitted package is not ready for deterministic grading."""


class LifecycleSession(Protocol):
    def add(self, record: object) -> None: ...

    def flush(self) -> None: ...

    def get(self, entity: object, ident: object) -> object | None: ...

    def execute(self, statement: object) -> Any: ...


@dataclass(frozen=True)
class IntakeValidationSummary:
    submission_id: UUID | None
    evidence_count: int
    warnings: tuple[str, ...] = ()


def create_draft_submission(
    db: LifecycleSession,
    *,
    organization_id: UUID,
    learner_id: UUID,
    assessment_id: UUID | None = None,
    assessment_item_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    actor_source: str = "learner",
    metadata_payload: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> Submission:
    if assessment_id is None and assessment_item_id is None:
        raise AnswerLifecycleError("Submission requires assessment_id or assessment_item_id.")

    submission = Submission(
        organization_id=organization_id,
        learner_id=learner_id,
        assessment_id=assessment_id,
        assessment_item_id=assessment_item_id,
        status=SUBMISSION_DRAFT,
        metadata_payload=copy.deepcopy(metadata_payload) if metadata_payload is not None else {},
    )
    db.add(submission)
    db.flush()
    _audit_submission_event(
        db,
        submission=submission,
        action="submission.created",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state={},
        new_state=_submission_state(submission),
        request_id=request_id,
    )
    db.flush()
    return submission


def add_submission_evidence(
    db: LifecycleSession,
    *,
    submission: Submission,
    evidence_type_id: UUID,
    raw_text: str | None = None,
    value_payload: dict[str, Any] | None = None,
    file_artifact_id: UUID | None = None,
    evidence_extraction_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    actor_source: str = "learner",
    request_id: str | None = None,
) -> SubmissionEvidence:
    ensure_submission_content_mutable(submission)
    _validate_evidence_payload(raw_text=raw_text, value_payload=value_payload, file_artifact_id=file_artifact_id)

    evidence = SubmissionEvidence(
        organization_id=submission.organization_id,
        submission_id=submission.id,
        evidence_type_id=evidence_type_id,
        raw_text=raw_text,
        value_payload=copy.deepcopy(value_payload) if value_payload is not None else {},
        file_artifact_id=file_artifact_id,
        evidence_extraction_id=evidence_extraction_id,
        status="submitted",
    )
    db.add(evidence)
    db.flush()
    _audit_submission_event(
        db,
        submission=submission,
        action="submission.evidence_added",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state={},
        new_state={
            "evidence_id": str(evidence.id) if evidence.id is not None else None,
            "evidence_type_id": str(evidence_type_id),
            "status": evidence.status,
        },
        request_id=request_id,
    )
    db.flush()
    return evidence


def submit_submission(
    db: LifecycleSession,
    *,
    submission: Submission,
    actor_user_id: UUID | None = None,
    actor_source: str = "learner",
    reason: str | None = None,
    request_id: str | None = None,
    superseded_submission: Submission | None = None,
) -> Submission:
    if submission.status != SUBMISSION_DRAFT:
        raise AnswerLifecycleError("Only draft answer packages can be submitted.")

    _validate_submission_context(submission)
    _validate_submission_evidence(submission)

    previous_package = superseded_submission or _load_superseded_package(db, submission)
    _ensure_no_other_current_package(
        db,
        submission,
        allowed_current_submission_id=previous_package.id if previous_package is not None else None,
    )

    previous_state = _submission_state(submission)
    submission.status = SUBMISSION_SUBMITTED
    submission.submitted_at = _now()
    _audit_submission_event(
        db,
        submission=submission,
        action="submission.submitted",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state=previous_state,
        new_state=_submission_state(submission),
        reason=reason,
        request_id=request_id,
    )
    _audit_submission_event(
        db,
        submission=submission,
        action="submission.evidence_sealed",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state={},
        new_state={"evidence_count": len(submission.evidence)},
        request_id=request_id,
    )

    if previous_package is not None:
        supersede_submission_package(
            db,
            previous_submission=previous_package,
            replacement_submission=submission,
            actor_user_id=actor_user_id,
            actor_source=actor_source,
            reason=reason or "Revision package submitted.",
            request_id=request_id,
        )

    db.flush()
    return submission


def request_learner_revision(
    db: LifecycleSession,
    *,
    submission: Submission,
    actor_user_id: UUID | None = None,
    actor_source: str = "teacher",
    reason: str,
    request_id: str | None = None,
    metadata_payload: dict[str, Any] | None = None,
) -> Submission:
    if submission.status != SUBMISSION_SUBMITTED:
        raise AnswerLifecycleError("Learner revisions can only be requested for submitted packages.")
    if not reason.strip():
        raise AnswerLifecycleError("Learner revision requests require a reason.")

    revision_metadata = copy.deepcopy(metadata_payload) if metadata_payload is not None else {}
    revision_metadata.setdefault("revision_of_submission_id", str(submission.id))
    revision_metadata.setdefault("revision_reason", reason)

    revision = Submission(
        organization_id=submission.organization_id,
        assessment_id=submission.assessment_id,
        assessment_item_id=submission.assessment_item_id,
        learner_id=submission.learner_id,
        supersedes_submission_id=submission.id,
        status=SUBMISSION_DRAFT,
        metadata_payload=revision_metadata,
    )
    db.add(revision)
    db.flush()

    _audit_submission_event(
        db,
        submission=submission,
        action="submission.revision_requested",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state=_submission_state(submission),
        new_state={"revision_submission_id": str(revision.id) if revision.id is not None else None},
        reason=reason,
        request_id=request_id,
    )
    _audit_submission_event(
        db,
        submission=revision,
        action="submission.revision_package_created",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state={},
        new_state=_submission_state(revision),
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return revision


def supersede_submission_package(
    db: LifecycleSession,
    *,
    previous_submission: Submission,
    replacement_submission: Submission,
    actor_user_id: UUID | None = None,
    actor_source: str = "system",
    reason: str | None = None,
    request_id: str | None = None,
) -> Submission:
    if previous_submission.status != SUBMISSION_SUBMITTED:
        raise AnswerLifecycleError("Only submitted answer packages can be superseded.")
    if replacement_submission.status != SUBMISSION_SUBMITTED:
        raise AnswerLifecycleError("Replacement answer package must be submitted before superseding.")
    if previous_submission.id == replacement_submission.id:
        raise AnswerLifecycleError("An answer package cannot supersede itself.")
    if previous_submission.organization_id != replacement_submission.organization_id:
        raise AnswerLifecycleError("Superseding packages must belong to the same organization.")
    if previous_submission.learner_id != replacement_submission.learner_id:
        raise AnswerLifecycleError("Superseding packages must belong to the same learner.")
    if previous_submission.assessment_id != replacement_submission.assessment_id:
        raise AnswerLifecycleError("Superseding packages must share assessment context.")
    if previous_submission.assessment_item_id != replacement_submission.assessment_item_id:
        raise AnswerLifecycleError("Superseding packages must share assessment item context.")

    previous_state = _submission_state(previous_submission)
    previous_submission.status = SUBMISSION_SUPERSEDED
    previous_submission.superseded_by_submission_id = replacement_submission.id
    replacement_submission.supersedes_submission_id = previous_submission.id
    _audit_submission_event(
        db,
        submission=previous_submission,
        action="submission.superseded",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state=previous_state,
        new_state=_submission_state(previous_submission),
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return previous_submission


def withdraw_submission(
    db: LifecycleSession,
    *,
    submission: Submission,
    actor_user_id: UUID | None = None,
    actor_source: str,
    reason: str,
    request_id: str | None = None,
) -> Submission:
    if submission.status not in {SUBMISSION_DRAFT, SUBMISSION_SUBMITTED}:
        raise AnswerLifecycleError("Only draft or submitted answer packages can be withdrawn.")
    previous_state = _submission_state(submission)
    submission.status = SUBMISSION_WITHDRAWN
    _audit_submission_event(
        db,
        submission=submission,
        action="submission.withdrawn",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state=previous_state,
        new_state=_submission_state(submission),
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return submission


def archive_submission(
    db: LifecycleSession,
    *,
    submission: Submission,
    actor_user_id: UUID | None = None,
    actor_source: str,
    reason: str,
    request_id: str | None = None,
) -> Submission:
    if submission.status == SUBMISSION_ARCHIVED:
        raise AnswerLifecycleError("Submission is already archived.")
    previous_state = _submission_state(submission)
    submission.status = SUBMISSION_ARCHIVED
    _audit_submission_event(
        db,
        submission=submission,
        action="submission.archived",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state=previous_state,
        new_state=_submission_state(submission),
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return submission


def request_regrade(
    db: LifecycleSession,
    *,
    submission: Submission,
    organization_id: UUID | None = None,
    rubric_version_id: UUID | None = None,
    answer_key_version_id: UUID | None = None,
    grading_policy_version: str | None = None,
    triggered_by_user_id: UUID | None = None,
    trigger_source: str = "teacher",
    reason: str,
    request_id: str | None = None,
    context_payload: dict[str, Any] | None = None,
) -> GradingRun:
    if submission.status != SUBMISSION_SUBMITTED:
        raise AnswerLifecycleError("Regrade requires a submitted immutable answer package.")
    if not reason.strip():
        raise AnswerLifecycleError("Regrade requests require a reason.")

    payload = copy.deepcopy(context_payload) if context_payload is not None else {}
    payload.setdefault("reason", reason)
    run = GradingRun(
        organization_id=organization_id or submission.organization_id,
        submission_id=submission.id,
        rubric_version_id=rubric_version_id,
        answer_key_version_id=answer_key_version_id,
        triggered_by_user_id=triggered_by_user_id,
        trigger_source=trigger_source,
        status="queued",
        grading_policy_version=grading_policy_version,
        context_payload=payload,
    )
    db.add(run)
    db.flush()
    _audit_submission_event(
        db,
        submission=submission,
        action="grading.regrade_requested",
        actor_user_id=triggered_by_user_id,
        actor_source=trigger_source,
        previous_state={},
        new_state={
            "grading_run_id": str(run.id) if run.id is not None else None,
            "rubric_version_id": str(rubric_version_id) if rubric_version_id is not None else None,
            "answer_key_version_id": str(answer_key_version_id) if answer_key_version_id is not None else None,
        },
        reason=reason,
        request_id=request_id,
        grading_run_id=run.id,
    )
    db.flush()
    return run


def supersede_grading_result(
    db: LifecycleSession,
    *,
    previous_result: GradingResult,
    replacement_result: GradingResult,
    submission: Submission,
    actor_user_id: UUID | None = None,
    actor_source: str = "system",
    reason: str | None = None,
    request_id: str | None = None,
) -> GradingResult:
    if previous_result.id == replacement_result.id:
        raise AnswerLifecycleError("A grading result cannot supersede itself.")
    previous_state = {"status": previous_result.status, "result_type": previous_result.result_type}
    previous_result.status = GRADING_RESULT_SUPERSEDED
    _audit_submission_event(
        db,
        submission=submission,
        action="grading_result.superseded",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        entity_type="grading_result",
        entity_id=previous_result.id,
        previous_state=previous_state,
        new_state={
            "status": previous_result.status,
            "replacement_grading_result_id": str(replacement_result.id) if replacement_result.id is not None else None,
        },
        reason=reason,
        request_id=request_id,
        grading_run_id=previous_result.grading_run_id,
    )
    db.flush()
    return previous_result


def validate_submission_ready_for_grading(
    submission: Submission,
    *,
    rubric_version_id: UUID | None = None,
    answer_key_version_id: UUID | None = None,
    answer_key_required: bool = False,
) -> IntakeValidationSummary:
    if submission.status != SUBMISSION_SUBMITTED:
        raise SubmissionIntakeError("Only submitted answer packages can be graded.")
    _validate_submission_context(submission)
    _validate_submission_evidence(submission)
    if rubric_version_id is None:
        raise SubmissionIntakeError("A rubric version or resolved rubric binding is required before grading.")
    if answer_key_required and answer_key_version_id is None:
        raise SubmissionIntakeError("An answer key version is required for deterministic answer-key grading.")
    return IntakeValidationSummary(
        submission_id=submission.id,
        evidence_count=len(submission.evidence),
    )


def ensure_submission_content_mutable(submission: Submission) -> None:
    if submission.status != SUBMISSION_DRAFT:
        raise SubmissionImmutableError("Submitted answer package content is immutable; create a revision package.")


def _validate_submission_context(submission: Submission) -> None:
    if submission.assessment_id is None and submission.assessment_item_id is None:
        raise AnswerLifecycleError("Submission requires assessment_id or assessment_item_id.")


def _validate_submission_evidence(submission: Submission) -> None:
    if not submission.evidence:
        raise SubmissionIntakeError("Submission requires at least one evidence record.")
    for evidence in submission.evidence:
        _validate_evidence_payload(
            raw_text=evidence.raw_text,
            value_payload=evidence.value_payload,
            file_artifact_id=evidence.file_artifact_id,
        )


def _validate_evidence_payload(
    *,
    raw_text: str | None,
    value_payload: dict[str, Any] | None,
    file_artifact_id: UUID | None,
) -> None:
    if raw_text is not None and raw_text.strip():
        return
    if file_artifact_id is not None:
        return
    if value_payload:
        return
    raise SubmissionIntakeError("Submission evidence requires raw text, file artifact, or structured value payload.")


def _load_superseded_package(db: LifecycleSession, submission: Submission) -> Submission | None:
    if submission.supersedes_submission_id is None:
        return None
    package = db.get(Submission, submission.supersedes_submission_id)
    if package is not None and not isinstance(package, Submission):
        raise AnswerLifecycleError("Superseded package lookup returned an unexpected record type.")
    return package


def _ensure_no_other_current_package(
    db: LifecycleSession,
    submission: Submission,
    *,
    allowed_current_submission_id: UUID | None,
) -> None:
    statement = (
        select(Submission)
        .where(Submission.organization_id == submission.organization_id)
        .where(Submission.learner_id == submission.learner_id)
        .where(Submission.status == SUBMISSION_SUBMITTED)
        .where(Submission.id != submission.id)
    )
    if submission.assessment_id is None:
        statement = statement.where(Submission.assessment_id.is_(None))
    else:
        statement = statement.where(Submission.assessment_id == submission.assessment_id)
    if submission.assessment_item_id is None:
        statement = statement.where(Submission.assessment_item_id.is_(None))
    else:
        statement = statement.where(Submission.assessment_item_id == submission.assessment_item_id)

    existing = db.execute(statement).scalars().first()
    if existing is None:
        return
    if not isinstance(existing, Submission):
        raise AnswerLifecycleError("Current package lookup returned an unexpected record type.")
    if allowed_current_submission_id is not None and existing.id == allowed_current_submission_id:
        return
    raise AnswerLifecycleError("A current submitted answer package already exists for this learner and context.")


def _audit_submission_event(
    db: LifecycleSession,
    *,
    submission: Submission,
    action: str,
    actor_user_id: UUID | None,
    actor_source: str,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    entity_type: str = "submission",
    entity_id: UUID | None = None,
    reason: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    grading_run_id: UUID | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=submission.organization_id,
        assessment_id=submission.assessment_id,
        submission_id=submission.id,
        grading_run_id=grading_run_id,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id if entity_id is not None else submission.id,
        request_id=request_id,
        job_id=job_id,
        previous_state=copy.deepcopy(previous_state),
        new_state=copy.deepcopy(new_state),
        reason=reason,
    )
    db.add(event)
    return event


def _submission_state(submission: Submission) -> dict[str, Any]:
    return {
        "id": str(submission.id) if submission.id is not None else None,
        "status": submission.status,
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at is not None else None,
        "supersedes_submission_id": (
            str(submission.supersedes_submission_id) if submission.supersedes_submission_id is not None else None
        ),
        "superseded_by_submission_id": (
            str(submission.superseded_by_submission_id) if submission.superseded_by_submission_id is not None else None
        ),
    }


def _now() -> datetime:
    return datetime.now(UTC)
