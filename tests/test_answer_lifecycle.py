import uuid

import pytest
from sqlalchemy import CheckConstraint

from app.db.models import AuditEvent, GradingResult, GradingRun, Submission, SubmissionEvidence
from app.db.services.answer_lifecycle import (
    AnswerLifecycleError,
    SubmissionImmutableError,
    SubmissionIntakeError,
    add_submission_evidence,
    archive_submission,
    create_draft_submission,
    request_learner_revision,
    request_regrade,
    submit_submission,
    supersede_grading_result,
    supersede_submission_package,
    validate_submission_ready_for_grading,
    withdraw_submission,
)


class RecordingSession:
    def __init__(self, get_result: object | None = None, current_package: object | None = None) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.get_result = get_result
        self.current_package = current_package

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        self.flush_count += 1
        for record in self.added:
            if hasattr(record, "id") and record.id is None:
                record.id = uuid.uuid4()

    def get(self, entity: object, ident: object) -> object | None:
        _ = (entity, ident)
        return self.get_result

    def execute(self, statement: object) -> object:
        _ = statement
        return ScalarResultEnvelope(self.current_package)


class ScalarResultEnvelope:
    def __init__(self, record: object | None) -> None:
        self.record = record

    def scalars(self) -> "ScalarResultEnvelope":
        return self

    def first(self) -> object | None:
        return self.record


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


def test_submit_blocks_second_current_package_for_same_context() -> None:
    current = make_submission(status="submitted")
    duplicate = make_submission(status="draft")
    duplicate.organization_id = current.organization_id
    duplicate.learner_id = current.learner_id
    duplicate.assessment_id = current.assessment_id
    duplicate.assessment_item_id = current.assessment_item_id
    session = RecordingSession(current_package=current)

    with pytest.raises(AnswerLifecycleError, match="current submitted answer package already exists"):
        submit_submission(session, submission=duplicate, actor_source="learner")  # type: ignore[arg-type]

    assert duplicate.status == "draft"
    assert audit_events(session) == []


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
    event = audit_events(session)[0]
    assert event.action == "grading_result.superseded"
    assert event.entity_type == "grading_result"
    assert event.entity_id == previous.id
    assert event.submission_id == submission.id


def test_text_response_exercise_revises_by_creating_new_package() -> None:
    session = RecordingSession()
    organization_id = uuid.uuid4()
    learner_id = uuid.uuid4()
    assessment_item_id = uuid.uuid4()
    evidence_type_id = uuid.uuid4()
    initial_answer = "Deterministic checks are useful because they are simple."
    revised_answer = (
        "Deterministic validation should run before AI-assisted grading because it catches missing evidence, "
        "malformed data, and clear objective matches in a repeatable way."
    )

    original = create_draft_submission(
        session,  # type: ignore[arg-type]
        organization_id=organization_id,
        learner_id=learner_id,
        assessment_item_id=assessment_item_id,
        actor_source="teacher",
        metadata_payload={"exercise": "short_response", "profile": "needs_revision"},
    )
    add_submission_evidence(  # type: ignore[arg-type]
        session,
        submission=original,
        evidence_type_id=evidence_type_id,
        raw_text=initial_answer,
        actor_source="learner",
    )
    original.evidence = [record for record in session.added if isinstance(record, SubmissionEvidence)]

    submit_submission(session, submission=original, actor_source="learner")  # type: ignore[arg-type]

    revision = request_learner_revision(  # type: ignore[arg-type]
        session,
        submission=original,
        actor_source="teacher",
        reason="Initial answer needs more concrete validation detail.",
        metadata_payload={"exercise": "short_response", "profile": "revised_valid"},
    )
    add_submission_evidence(  # type: ignore[arg-type]
        session,
        submission=revision,
        evidence_type_id=evidence_type_id,
        raw_text=revised_answer,
        actor_source="learner",
    )
    revision.evidence = [
        record
        for record in session.added
        if isinstance(record, SubmissionEvidence) and record.submission_id == revision.id
    ]

    submit_submission(
        session,  # type: ignore[arg-type]
        submission=revision,
        actor_source="learner",
        superseded_submission=original,
    )

    assert original.status == "superseded"
    assert revision.status == "submitted"
    assert revision.supersedes_submission_id == original.id
    assert original.superseded_by_submission_id == revision.id
    assert original.evidence[0].raw_text == initial_answer
    assert revision.evidence[0].raw_text == revised_answer
    assert validate_submission_ready_for_grading(revision, rubric_version_id=uuid.uuid4()).evidence_count == 1
    assert "submission.superseded" in [event.action for event in audit_events(session)]


def test_revision_request_requires_submitted_package_and_reason() -> None:
    draft = make_submission(status="draft")
    submitted = make_submission(status="submitted")

    with pytest.raises(AnswerLifecycleError, match="submitted packages"):
        request_learner_revision(  # type: ignore[arg-type]
            RecordingSession(),
            submission=draft,
            actor_source="teacher",
            reason="Needs revision.",
        )

    with pytest.raises(AnswerLifecycleError, match="require a reason"):
        request_learner_revision(  # type: ignore[arg-type]
            RecordingSession(),
            submission=submitted,
            actor_source="teacher",
            reason=" ",
        )


def test_regrade_requires_submitted_package_and_reason() -> None:
    draft = make_submission(status="draft")
    submitted = make_submission(status="submitted")

    with pytest.raises(AnswerLifecycleError, match="submitted immutable"):
        request_regrade(  # type: ignore[arg-type]
            RecordingSession(),
            submission=draft,
            reason="Rubric version changed.",
        )

    with pytest.raises(AnswerLifecycleError, match="require a reason"):
        request_regrade(  # type: ignore[arg-type]
            RecordingSession(),
            submission=submitted,
            reason=" ",
        )


def test_superseding_requires_matching_context_and_submitted_replacement() -> None:
    original = make_submission(status="submitted")
    replacement = make_submission(status="draft")
    replacement.organization_id = original.organization_id
    replacement.learner_id = original.learner_id
    replacement.assessment_id = original.assessment_id
    replacement.assessment_item_id = original.assessment_item_id

    with pytest.raises(AnswerLifecycleError, match="must be submitted"):
        supersede_submission_package(  # type: ignore[arg-type]
            RecordingSession(),
            previous_submission=original,
            replacement_submission=replacement,
        )

    replacement.status = "submitted"
    replacement.learner_id = uuid.uuid4()
    with pytest.raises(AnswerLifecycleError, match="same learner"):
        supersede_submission_package(  # type: ignore[arg-type]
            RecordingSession(),
            previous_submission=original,
            replacement_submission=replacement,
        )


def test_withdraw_and_archive_create_audit_events() -> None:
    withdrawn_session = RecordingSession()
    draft = make_submission(status="draft")

    withdraw_submission(  # type: ignore[arg-type]
        withdrawn_session,
        submission=draft,
        actor_source="teacher",
        reason="Imported draft was cancelled.",
    )

    assert draft.status == "withdrawn"
    assert audit_events(withdrawn_session)[0].action == "submission.withdrawn"

    archived_session = RecordingSession()
    submitted = make_submission(status="submitted")
    archive_submission(  # type: ignore[arg-type]
        archived_session,
        submission=submitted,
        actor_source="admin",
        reason="Assessment closed.",
    )

    assert submitted.status == "archived"
    assert audit_events(archived_session)[0].action == "submission.archived"
