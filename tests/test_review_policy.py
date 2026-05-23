import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.db.models import AuditEvent, CriterionResult, GradingResult, ReviewTask, Submission
from app.db.models.review import TeacherReview
from app.db.services.review_policy import (
    ReviewPolicyError,
    adjust_review_score,
    approve_review_result,
    edit_review_feedback,
    override_criterion_result,
    return_review_for_regrade,
)


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        self.flush_count += 1
        for record in self.added:
            if hasattr(record, "id") and record.id is None:
                record.id = uuid.uuid4()


def records(session: RecordingSession, record_type: type) -> list:
    return [record for record in session.added if isinstance(record, record_type)]


def make_review_context() -> tuple[Submission, GradingResult, ReviewTask]:
    organization_id = uuid.uuid4()
    submission = Submission(
        id=uuid.uuid4(),
        organization_id=organization_id,
        learner_id=uuid.uuid4(),
        assessment_id=uuid.uuid4(),
        assessment_item_id=uuid.uuid4(),
        status="submitted",
        metadata_payload={},
    )
    grading_result = GradingResult(
        id=uuid.uuid4(),
        organization_id=organization_id,
        grading_run_id=uuid.uuid4(),
        rubric_version_id=uuid.uuid4(),
        answer_key_version_id=uuid.uuid4(),
        result_type="proposed",
        status="needs_review",
        total_score=Decimal("4"),
        max_score=Decimal("6"),
        confidence=Decimal("0.72"),
        feedback="Automated draft feedback.",
        explanation_payload={
            "routing": {"decision": "route_to_review", "reasons": ["confidence_below_threshold"]},
            "review_reasons": ["confidence_below_threshold"],
            "policy": {"grading_policy_version": "phase-1-default"},
        },
    )
    review_task = ReviewTask(
        id=uuid.uuid4(),
        organization_id=organization_id,
        assessment_id=submission.assessment_id,
        assessment_item_id=submission.assessment_item_id,
        submission_id=submission.id,
        grading_run_id=grading_result.grading_run_id,
        grading_result_id=grading_result.id,
        status="open",
        priority="normal",
        confidence_band="medium",
        escalation_reason="confidence_below_threshold",
        policy_payload={"reasons": ["confidence_below_threshold"]},
    )
    return submission, grading_result, review_task


def test_approve_review_finalizes_as_human_reviewed_result() -> None:
    session = RecordingSession()
    submission, grading_result, review_task = make_review_context()
    reviewer_id = uuid.uuid4()

    outcome = approve_review_result(
        session,
        review_task=review_task,
        grading_result=grading_result,
        submission=submission,
        reviewer_id=reviewer_id,
        reason="Evidence supports the automated result.",
        request_id="req-review-approve",
    )

    assert outcome.teacher_review.decision == "approve"
    assert outcome.teacher_review.comments == "Evidence supports the automated result."
    assert review_task.status == "completed"
    assert grading_result.status == "finalized"
    assert grading_result.result_type == "reviewed"
    assert grading_result.confidence == Decimal("0.72")
    assert grading_result.explanation_payload["finalization"]["source"] == "teacher_review"
    assert records(session, TeacherReview) == [outcome.teacher_review]
    audit = records(session, AuditEvent)[0]
    assert audit.action == "teacher_review.completed"
    assert audit.actor_user_id == reviewer_id
    assert audit.request_id == "req-review-approve"


def test_adjust_review_score_records_override_and_previous_value() -> None:
    session = RecordingSession()
    submission, grading_result, review_task = make_review_context()
    reviewer_id = uuid.uuid4()

    outcome = adjust_review_score(
        session,
        review_task=review_task,
        grading_result=grading_result,
        submission=submission,
        reviewer_id=reviewer_id,
        final_score=Decimal("5"),
        reason="Awarded credit for the alternative explanation.",
    )

    assert outcome.teacher_review.decision == "adjust"
    assert outcome.teacher_review.final_score == Decimal("5")
    assert outcome.teacher_override is not None
    assert outcome.teacher_override.override_type == "score"
    assert outcome.teacher_override.previous_payload == {"total_score": "4"}
    assert outcome.teacher_override.new_payload == {"total_score": "5"}
    assert grading_result.total_score == Decimal("5")
    assert grading_result.status == "finalized"
    assert grading_result.result_type == "overridden"
    assert review_task.status == "completed"
    assert [event.action for event in records(session, AuditEvent)] == [
        "teacher_review.completed",
        "teacher_override.applied",
    ]


def test_edit_review_feedback_records_feedback_override() -> None:
    session = RecordingSession()
    submission, grading_result, review_task = make_review_context()

    outcome = edit_review_feedback(
        session,
        review_task=review_task,
        grading_result=grading_result,
        submission=submission,
        reviewer_id=uuid.uuid4(),
        feedback="Revised teacher feedback.",
        reason="Feedback should mention the missing edge case.",
    )

    assert outcome.teacher_review.decision == "override"
    assert outcome.teacher_override is not None
    assert outcome.teacher_override.override_type == "feedback"
    assert outcome.teacher_override.previous_payload == {"feedback": "Automated draft feedback."}
    assert outcome.teacher_override.new_payload == {"feedback": "Revised teacher feedback."}
    assert grading_result.feedback == "Revised teacher feedback."
    assert grading_result.result_type == "overridden"


def test_override_criterion_result_adds_teacher_source_without_mutating_original() -> None:
    session = RecordingSession()
    submission, grading_result, review_task = make_review_context()
    original = CriterionResult(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        grading_result_id=grading_result.id,
        criterion_key="correctness",
        source="ai",
        score=Decimal("1"),
        max_score=Decimal("4"),
        confidence=Decimal("0.62"),
        explanation="AI was uncertain.",
        metadata_payload={"evidence_references": ["ev1"]},
    )

    outcome = override_criterion_result(
        session,
        review_task=review_task,
        grading_result=grading_result,
        submission=submission,
        reviewer_id=uuid.uuid4(),
        criterion_key="correctness",
        score=Decimal("3"),
        max_score=Decimal("4"),
        explanation="Teacher accepted most of the reasoning.",
        reason="Manual review found valid partial credit.",
        previous_criterion_result=original,
        metadata_payload={"selected_level": "partial"},
    )

    teacher_criteria = records(session, CriterionResult)
    assert len(teacher_criteria) == 1
    assert teacher_criteria[0].source == "teacher"
    assert teacher_criteria[0].criterion_key == "correctness"
    assert teacher_criteria[0].score == Decimal("3")
    assert original.score == Decimal("1")
    assert outcome.teacher_override is not None
    assert outcome.teacher_override.override_type == "criterion_result"
    assert outcome.teacher_override.previous_payload["source"] == "ai"
    assert outcome.teacher_override.new_payload["score"] == "3"
    assert grading_result.result_type == "overridden"


def test_return_for_regrade_records_decision_and_creates_new_run() -> None:
    session = RecordingSession()
    submission, grading_result, review_task = make_review_context()
    reviewer_id = uuid.uuid4()

    outcome = return_review_for_regrade(
        session,
        review_task=review_task,
        grading_result=grading_result,
        submission=submission,
        reviewer_id=reviewer_id,
        reason="Answer key rule was configured incorrectly.",
        request_id="req-regrade",
    )

    assert outcome.teacher_review.decision == "return_for_regrade"
    assert review_task.status == "completed"
    assert grading_result.status == "needs_review"
    assert outcome.regrade_run is not None
    assert outcome.regrade_run.status == "queued"
    assert outcome.regrade_run.triggered_by_user_id == reviewer_id
    assert outcome.regrade_run.context_payload["previous_grading_result_id"] == str(grading_result.id)
    assert [event.action for event in records(session, AuditEvent)] == [
        "grading.regrade_requested",
        "teacher_review.returned_for_regrade",
    ]


@pytest.mark.parametrize(
    ("mutations", "message"),
    [
        ({"task_status": "completed"}, "not open"),
        ({"result_status": "finalized"}, "need review"),
        ({"reason": ""}, "require a reason"),
    ],
)
def test_review_actions_validate_state_and_reason(mutations: dict[str, Any], message: str) -> None:
    session = RecordingSession()
    submission, grading_result, review_task = make_review_context()
    review_task.status = mutations.get("task_status", review_task.status)
    grading_result.status = mutations.get("result_status", grading_result.status)
    reason = mutations.get("reason", "Looks correct.")

    with pytest.raises(ReviewPolicyError, match=message):
        approve_review_result(
            session,
            review_task=review_task,
            grading_result=grading_result,
            submission=submission,
            reviewer_id=uuid.uuid4(),
            reason=reason,
        )
