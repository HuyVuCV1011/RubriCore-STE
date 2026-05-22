import uuid

import pytest
from sqlalchemy import CheckConstraint

from app.db.models import AuditEvent, GradingResult, GradingRun, Submission, SubmissionEvidence
from app.db.services.answer_lifecycle import (
    AnswerLifecycleError,
    SubmissionImmutableError,
    SubmissionIntakeError,
    add_submission_evidence,
    create_draft_submission,
    request_learner_revision,
    request_regrade,
    submit_submission,
    supersede_grading_result,
    validate_submission_ready_for_grading,
)


class RecordingSession:
    def __init__(self, get_result: object | None = None) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.get_result = get_result

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        self.flush_count += 1

    def get(self, entity: object, ident: object) -> object | None:
        _ = (entity, ident)
        return self.get_result


def make_submission(*, status: str = "draft", evidence_count: int = 1) -> Submission:
    submission = Submission(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        learner_id=uuid.uuid4(),
        assessment_item_id=uuid.uuid4(),
        status=status,
        metadata_payload={},
    )
    submission.evidence = [
        SubmissionEvidence(
            id=uuid.uuid4(),
            organization_id=submission.organization_id,
            submission_id=submission.id,
            evidence_type_id=uuid.uuid4(),
            raw_text=f"answer {index}",
            value_payload={},
            status="submitted",
        )
        for index in range(evidence_count)
    ]
    return submission


def audit_events(session: RecordingSession) -> list[AuditEvent]:
    return [record for record in session.added if isinstance(record, AuditEvent)]


def test_submission_lifecycle_columns_and_states_are_registered() -> None:
    columns = Submission.__table__.columns
    assert "supersedes_submission_id" in columns
    assert "superseded_by_submission_id" in columns
    assert columns["status"].default.arg == "draft"

    constraint_sql = {
        str(constraint.sqltext)
        for constraint in Submission.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name
    }

    assert (
        "status in ('draft', 'submitted', 'superseded', 'withdrawn', 'archived', "
        "'processing', 'graded', 'returned')"
    ) in constraint_sql
    assert "superseded_by_submission_id is null or status = 'superseded'" in constraint_sql


def test_create_draft_submission_records_creation_audit_event() -> None:
    session = RecordingSession()
    organization_id = uuid.uuid4()
    learner_id = uuid.uuid4()
    assessment_item_id = uuid.uuid4()

    submission = create_draft_submission(
        session,  # type: ignore[arg-type]
        organization_id=organization_id,
        learner_id=learner_id,
        assessment_item_id=assessment_item_id,
        actor_source="teacher",
        metadata_payload={"import_source": "synthetic_test"},
    )

    assert submission.status == "draft"
    assert submission.organization_id == organization_id
    assert submission.learner_id == learner_id
    assert submission.assessment_item_id == assessment_item_id
    assert submission.metadata_payload == {"import_source": "synthetic_test"}
    assert audit_events(session)[0].action == "submission.created"


def test_submit_draft_freezes_package_and_records_audit_events() -> None:
    session = RecordingSession()
    submission = make_submission(status="draft")

    submit_submission(session, submission=submission, actor_source="learner")  # type: ignore[arg-type]

    assert submission.status == "submitted"
    assert submission.submitted_at is not None
    assert [event.action for event in audit_events(session)] == [
        "submission.submitted",
        "submission.evidence_sealed",
    ]


def test_submitting_without_evidence_is_invalid() -> None:
    submission = make_submission(status="draft", evidence_count=0)

    with pytest.raises(SubmissionIntakeError, match="at least one evidence"):
        submit_submission(RecordingSession(), submission=submission)  # type: ignore[arg-type]


def test_submitted_package_content_is_immutable() -> None:
    submission = make_submission(status="submitted")

    with pytest.raises(SubmissionImmutableError, match="immutable"):
        add_submission_evidence(  # type: ignore[arg-type]
            RecordingSession(),
            submission=submission,
            evidence_type_id=uuid.uuid4(),
            raw_text="late replacement",
        )


def test_add_submission_evidence_allows_draft_mutation_and_audits() -> None:
    session = RecordingSession()
    submission = make_submission(status="draft", evidence_count=0)

    evidence = add_submission_evidence(  # type: ignore[arg-type]
        session,
        submission=submission,
        evidence_type_id=uuid.uuid4(),
        raw_text="draft answer",
    )

    assert evidence.status == "submitted"
    assert evidence.submission_id == submission.id
    assert audit_events(session)[0].action == "submission.evidence_added"


def test_request_learner_revision_creates_distinct_draft_package() -> None:
    session = RecordingSession()
    original = make_submission(status="submitted")

    revision = request_learner_revision(  # type: ignore[arg-type]
        session,
        submission=original,
        actor_source="teacher",
        reason="Evidence file is unreadable.",
    )

    assert original.status == "submitted"
    assert revision.status == "draft"
    assert revision.supersedes_submission_id == original.id
    assert revision.learner_id == original.learner_id
    assert [event.action for event in audit_events(session)] == [
        "submission.revision_requested",
        "submission.revision_package_created",
    ]


def test_submitting_revision_supersedes_original_package() -> None:
    original = make_submission(status="submitted")
    revision = make_submission(status="draft")
    revision.organization_id = original.organization_id
    revision.learner_id = original.learner_id
    revision.assessment_id = original.assessment_id
    revision.assessment_item_id = original.assessment_item_id
    revision.supersedes_submission_id = original.id
    session = RecordingSession(get_result=original)

    submit_submission(session, submission=revision, actor_source="learner")  # type: ignore[arg-type]

    assert revision.status == "submitted"
    assert original.status == "superseded"
    assert original.superseded_by_submission_id == revision.id
    assert "submission.superseded" in [event.action for event in audit_events(session)]


def test_invalid_transition_back_to_draft_is_rejected() -> None:
    submission = make_submission(status="submitted")

    with pytest.raises(AnswerLifecycleError, match="Only draft"):
        submit_submission(RecordingSession(), submission=submission)  # type: ignore[arg-type]


def test_intake_validation_requires_submitted_package_and_rubric_context() -> None:
    draft = make_submission(status="draft")

    with pytest.raises(SubmissionIntakeError, match="submitted"):
        validate_submission_ready_for_grading(draft, rubric_version_id=uuid.uuid4())

    submitted = make_submission(status="submitted")
    with pytest.raises(SubmissionIntakeError, match="rubric version"):
        validate_submission_ready_for_grading(submitted)

    with pytest.raises(SubmissionIntakeError, match="answer key version"):
        validate_submission_ready_for_grading(
            submitted,
            rubric_version_id=uuid.uuid4(),
            answer_key_required=True,
        )

    summary = validate_submission_ready_for_grading(
        submitted,
        rubric_version_id=uuid.uuid4(),
        answer_key_version_id=uuid.uuid4(),
        answer_key_required=True,
    )
    assert summary.submission_id == submitted.id
    assert summary.evidence_count == 1


def test_regrade_creates_new_grading_run_without_mutating_submission() -> None:
    session = RecordingSession()
    submission = make_submission(status="submitted")
    submitted_at = submission.submitted_at
    rubric_version_id = uuid.uuid4()
    answer_key_version_id = uuid.uuid4()

    run = request_regrade(  # type: ignore[arg-type]
        session,
        submission=submission,
        rubric_version_id=rubric_version_id,
        answer_key_version_id=answer_key_version_id,
        reason="Answer key version changed.",
    )

    assert isinstance(run, GradingRun)
    assert run.status == "queued"
    assert run.submission_id == submission.id
    assert run.rubric_version_id == rubric_version_id
    assert run.answer_key_version_id == answer_key_version_id
    assert submission.status == "submitted"
    assert submission.submitted_at == submitted_at
    assert audit_events(session)[0].action == "grading.regrade_requested"


def test_supersede_grading_result_marks_only_prior_result_superseded() -> None:
    session = RecordingSession()
    submission = make_submission(status="submitted")
    previous = GradingResult(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        grading_run_id=uuid.uuid4(),
        status="finalized",
        result_type="final",
    )
    replacement = GradingResult(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        grading_run_id=uuid.uuid4(),
        status="proposed",
        result_type="proposed",
    )

    supersede_grading_result(  # type: ignore[arg-type]
        session,
        previous_result=previous,
        replacement_result=replacement,
        submission=submission,
        reason="Regrade produced a newer result.",
    )

    assert previous.status == "superseded"
    assert replacement.status == "proposed"
    assert audit_events(session)[0].action == "grading_result.superseded"
