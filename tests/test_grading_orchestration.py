import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.db.models import (
    AIInteraction,
    AuditEvent,
    CriterionResult,
    GradingResult,
    GradingRun,
    RubricVersion,
    Submission,
    SubmissionEvidence,
)
from app.db.models.rubric import AnswerKeyVersion
from app.db.services.grading_orchestration import (
    AIOutputValidationError,
    GradingOrchestrationError,
    GradingPolicy,
    orchestrate_grading,
    start_grading_run,
    validate_ai_output,
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


class FakeAIProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.requests: list[dict[str, Any]] = []

    def evaluate(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request_payload)
        return self.output


def rubric_schema() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "criteria": [
            {"key": "correctness", "label": "Correctness", "position": 0, "weight": "2"},
            {"key": "clarity", "label": "Clarity", "position": 1, "weight": "1"},
        ],
        "performance_levels": [
            {"key": "needs_revision", "label": "Needs Revision", "position": 0, "score": "0"},
            {"key": "partial", "label": "Partial", "position": 1, "score": "1"},
            {"key": "meets", "label": "Meets", "position": 2, "score": "2"},
        ],
        "descriptors": [
            {
                "criterion_key": "correctness",
                "performance_level_key": "needs_revision",
                "narrative": "Does not compute the requested result.",
            },
            {
                "criterion_key": "correctness",
                "performance_level_key": "partial",
                "narrative": "Computes the main path but misses edge cases.",
            },
            {
                "criterion_key": "correctness",
                "performance_level_key": "meets",
                "narrative": "Computes the requested result accurately.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "needs_revision",
                "narrative": "The solution is difficult to inspect.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "partial",
                "narrative": "The solution is readable in parts.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "meets",
                "narrative": "The solution is clear and direct.",
            },
        ],
    }


def make_submission(*, status: str = "submitted") -> Submission:
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
            raw_text="Deterministic checks should run before AI.",
            value_payload={},
            status="submitted",
        )
    ]
    return submission


def make_rubric_version(submission: Submission, *, status: str = "published") -> RubricVersion:
    return RubricVersion(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        rubric_id=uuid.uuid4(),
        version_number=1,
        title="Phase 1 Rubric",
        rubric_schema=rubric_schema(),
        status=status,
    )


def make_answer_key_version(submission: Submission, *, status: str = "published") -> AnswerKeyVersion:
    return AnswerKeyVersion(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        answer_key_id=uuid.uuid4(),
        version_number=1,
        key_payload={"accepted": ["Deterministic checks should run before AI."]},
        status=status,
    )


def records(session: RecordingSession, record_type: type) -> list:
    return [record for record in session.added if isinstance(record, record_type)]


def test_start_grading_requires_submitted_package_and_published_rubric() -> None:
    draft = make_submission(status="draft")
    rubric = make_rubric_version(draft)

    with pytest.raises(Exception, match="submitted"):
        start_grading_run(RecordingSession(), submission=draft, rubric_version=rubric)

    submitted = make_submission()
    archived_rubric = make_rubric_version(submitted, status="archived")

    with pytest.raises(GradingOrchestrationError, match="published rubric"):
        start_grading_run(RecordingSession(), submission=submitted, rubric_version=archived_rubric)


def test_start_grading_requires_answer_key_when_deterministic_key_is_required() -> None:
    submission = make_submission()
    rubric = make_rubric_version(submission)

    with pytest.raises(Exception, match="answer key version"):
        start_grading_run(
            RecordingSession(),
            submission=submission,
            rubric_version=rubric,
            answer_key_required=True,
        )


def test_high_confidence_deterministic_result_auto_finalizes_without_ai() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    provider = FakeAIProvider(
        {
            "criterion_suggestions": [
                {"criterion_key": "correctness", "score": "0", "confidence": "0.95", "explanation": "Unused."}
            ],
            "confidence": "0.95",
        }
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        selected_levels_by_criterion={"correctness": "meets", "clarity": "partial"},
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=False),
    )

    assert provider.requests == []
    assert outcome.grading_run.status == "completed"
    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "finalized"
    assert outcome.grading_result.result_type == "final"
    assert outcome.grading_result.total_score == Decimal("5")
    assert outcome.grading_result.max_score == Decimal("6")
    assert outcome.review_task is None
    assert len(records(session, CriterionResult)) == 2
    assert [event.action for event in records(session, AuditEvent)] == [
        "grading_run.created",
        "grading_run.started",
        "grading.deterministic_checks_completed",
        "grading_result.auto_finalized",
        "grading_run.completed",
    ]


def test_ai_is_invoked_after_deterministic_stage_and_validation_is_recorded() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    provider = FakeAIProvider(
        {
            "criterion_suggestions": [
                {
                    "criterion_key": "correctness",
                    "score": "4",
                    "confidence": "0.95",
                    "explanation": "Matches deterministic result.",
                }
            ],
            "overall_feedback_draft": "Strong answer.",
            "confidence": "0.95",
        }
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        selected_levels_by_criterion={"correctness": "meets", "clarity": "partial"},
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=True),
    )

    assert provider.requests
    assert provider.requests[0]["deterministic"]["criterion_scores"]["correctness"] == "4"
    assert outcome.ai_interaction is not None
    assert outcome.ai_interaction.validation_status == "valid"
    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "finalized"
    assert len(records(session, AIInteraction)) == 1


def test_deterministic_ai_disagreement_routes_to_review() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    provider = FakeAIProvider(
        {
            "criterion_suggestions": [
                {
                    "criterion_key": "correctness",
                    "score": "0",
                    "confidence": "0.99",
                    "explanation": "Disagrees with deterministic level.",
                }
            ],
            "overall_feedback_draft": "Needs review.",
            "confidence": "0.99",
        }
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        selected_levels_by_criterion={"correctness": "meets", "clarity": "partial"},
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=True),
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "needs_review"
    assert outcome.review_task is not None
    assert outcome.review_task.escalation_reason == "deterministic_ai_disagreement"
    assert outcome.review_task.priority == "high"


def test_invalid_ai_output_is_not_used_for_scores_and_routes_to_review() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    provider = FakeAIProvider({"criterion_suggestions": [{"criterion_key": "missing", "score": "1"}]})

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        selected_levels_by_criterion={"correctness": "meets"},
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=True, ai_required=True),
    )

    assert outcome.ai_interaction is not None
    assert outcome.ai_interaction.validation_status == "invalid"
    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "needs_review"
    assert outcome.review_task is not None
    assert outcome.review_task.escalation_reason == "ai_validation_failed"
    assert all(record.source == "deterministic" for record in records(session, CriterionResult))


def test_low_confidence_ai_only_result_routes_to_review() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    provider = FakeAIProvider(
        {
            "criterion_suggestions": [
                {
                    "criterion_key": "correctness",
                    "score": "1",
                    "confidence": "0.60",
                    "explanation": "Plausible but uncertain.",
                }
            ],
            "overall_feedback_draft": "Needs a teacher look.",
            "confidence": "0.60",
        }
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=True),
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "needs_review"
    assert outcome.grading_result.total_score == Decimal("1")
    assert outcome.review_task is not None
    assert outcome.review_task.escalation_reason == "partial_grading"


def test_high_confidence_ai_only_full_coverage_can_auto_finalize() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    provider = FakeAIProvider(
        {
            "criterion_suggestions": [
                {
                    "criterion_key": "correctness",
                    "score": "4",
                    "confidence": "0.95",
                    "explanation": "Complete and well supported.",
                },
                {
                    "criterion_key": "clarity",
                    "score": "2",
                    "confidence": "0.95",
                    "explanation": "Clear and direct.",
                },
            ],
            "overall_feedback_draft": "Strong answer.",
            "confidence": "0.95",
        }
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=True),
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "finalized"
    assert outcome.grading_result.confidence == Decimal("0.95")
    assert outcome.grading_result.explanation_payload["routing"]["decision"] == "auto_accept"
    assert outcome.review_task is None


def test_mandatory_review_overrides_high_confidence() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        selected_levels_by_criterion={"correctness": "meets", "clarity": "meets"},
        policy=GradingPolicy(mandatory_review=True),
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "needs_review"
    assert outcome.grading_result.confidence == Decimal("1")
    assert outcome.review_task is not None
    assert outcome.review_task.escalation_reason == "mandatory_review_policy"
    assert outcome.review_task.confidence_band == "high"
    assert outcome.grading_result.explanation_payload["routing"]["reasons"] == ["mandatory_review_policy"]


def test_high_confidence_incomplete_coverage_routes_to_review() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    provider = FakeAIProvider(
        {
            "criterion_suggestions": [
                {
                    "criterion_key": "correctness",
                    "score": "4",
                    "confidence": "0.97",
                    "explanation": "Correct, but clarity is missing.",
                }
            ],
            "overall_feedback_draft": "Incomplete rubric coverage.",
            "confidence": "0.97",
        }
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=True),
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "needs_review"
    assert outcome.grading_result.confidence == Decimal("0.97")
    assert outcome.review_task is not None
    assert outcome.review_task.escalation_reason == "partial_grading"
    assert "rubric_coverage_incomplete" in outcome.review_task.policy_payload["reasons"]
    coverage = outcome.grading_result.explanation_payload["rubric_coverage_summary"]
    assert coverage["missing_criterion_keys"] == ["clarity"]


def test_validate_ai_output_rejects_unknown_criterion_and_out_of_range_confidence() -> None:
    submission = make_submission()
    rubric = make_rubric_version(submission)

    with pytest.raises(AIOutputValidationError, match="unknown criterion"):
        validate_ai_output(
            {
                "criterion_suggestions": [
                    {
                        "criterion_key": "unknown",
                        "score": "1",
                        "confidence": "0.5",
                        "explanation": "Unknown.",
                    }
                ],
                "confidence": "0.5",
            },
            rubric_version=rubric,
        )

    with pytest.raises(AIOutputValidationError, match="between 0 and 1"):
        validate_ai_output(
            {
                "criterion_suggestions": [
                    {
                        "criterion_key": "correctness",
                        "score": "1",
                        "confidence": "1.5",
                        "explanation": "Too confident.",
                    }
                ],
                "confidence": "1.5",
            },
            rubric_version=rubric,
        )


def test_answer_key_version_is_captured_when_required() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    answer_key = make_answer_key_version(submission)

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        answer_key_version=answer_key,
        answer_key_required=True,
        selected_levels_by_criterion={"correctness": "meets"},
    )

    assert outcome.grading_run.answer_key_version_id == answer_key.id
    assert outcome.grading_result is not None
    assert outcome.grading_result.answer_key_version_id == answer_key.id
    assert records(session, GradingRun)[0].context_payload["ai_allowed"] is False
    assert records(session, GradingResult)[0].rubric_version_id == rubric.id
