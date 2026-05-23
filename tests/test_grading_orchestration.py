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
    ReviewTask,
    RubricVersion,
    Submission,
    SubmissionEvidence,
)
from app.db.models.rubric import AnswerKeyVersion, RubricBinding
from app.db.services.grading_orchestration import (
    AIOutputValidationError,
    GradingOrchestrationError,
    GradingPolicy,
    orchestrate_grading_for_submission,
    orchestrate_grading,
    resolve_grading_context,
    start_grading_run,
    validate_ai_output,
)


class RecordingSession:
    def __init__(
        self,
        *,
        scalar_results: list[object | None] | None = None,
        get_results: dict[tuple[object, object], object] | None = None,
    ) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.scalar_results = list(scalar_results or [])
        self.scalar_calls: list[object] = []
        self.get_results = get_results or {}

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        self.flush_count += 1
        for record in self.added:
            if hasattr(record, "id") and record.id is None:
                record.id = uuid.uuid4()

    def scalar(self, statement: object) -> object | None:
        self.scalar_calls.append(statement)
        if not self.scalar_results:
            return None
        return self.scalar_results.pop(0)

    def get(self, entity: object, ident: object) -> object | None:
        return self.get_results.get((entity, ident))


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


def make_rubric_binding(
    submission: Submission,
    rubric: RubricVersion,
    *,
    context_type: str = "assessment_item",
) -> RubricBinding:
    return RubricBinding(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        rubric_version_id=rubric.id,
        assessment_id=submission.assessment_id if context_type == "assessment" else None,
        assessment_item_id=submission.assessment_item_id if context_type == "assessment_item" else None,
        context_type=context_type,
        status="active",
    )


def make_answer_key_version(
    submission: Submission,
    *,
    status: str = "published",
    key_payload: dict[str, Any] | None = None,
) -> AnswerKeyVersion:
    return AnswerKeyVersion(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        answer_key_id=uuid.uuid4(),
        version_number=1,
        key_payload=key_payload or {"accepted": ["Deterministic checks should run before AI."]},
        status=status,
    )


def evidence_refs(submission: Submission) -> list[str]:
    return [str(submission.evidence[0].id)]


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


def test_resolve_grading_context_uses_explicit_rubric_without_binding_lookup() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)

    context = resolve_grading_context(session, submission=submission, rubric_version=rubric)

    assert context.rubric_version == rubric
    assert context.answer_key_version is None
    assert context.context_payload["rubric_selection_source"] == "explicit"
    assert context.context_payload["rubric_binding_id"] is None
    assert session.scalar_calls == []


def test_orchestrate_for_submission_resolves_assessment_item_binding() -> None:
    submission = make_submission()
    rubric = make_rubric_version(submission)
    binding = make_rubric_binding(submission, rubric)
    session = RecordingSession(
        scalar_results=[binding],
        get_results={(RubricVersion, rubric.id): rubric},
    )

    outcome = orchestrate_grading_for_submission(
        session,
        submission=submission,
        selected_levels_by_criterion={"correctness": "meets", "clarity": "partial"},
    )

    assert outcome.grading_run.rubric_version_id == rubric.id
    assert outcome.grading_run.context_payload["rubric_selection_source"] == "assessment_item_binding"
    assert outcome.grading_run.context_payload["rubric_binding_id"] == str(binding.id)
    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "finalized"


def test_resolve_grading_context_falls_back_to_assessment_binding() -> None:
    submission = make_submission()
    submission.assessment_id = uuid.uuid4()
    rubric = make_rubric_version(submission)
    binding = make_rubric_binding(submission, rubric, context_type="assessment")
    session = RecordingSession(
        scalar_results=[None, binding],
        get_results={(RubricVersion, rubric.id): rubric},
    )

    context = resolve_grading_context(session, submission=submission)

    assert context.rubric_version == rubric
    assert context.context_payload["rubric_selection_source"] == "assessment_binding"
    assert context.context_payload["rubric_binding_id"] == str(binding.id)
    assert len(session.scalar_calls) == 2


def test_resolve_grading_context_requires_explicit_rubric_or_active_binding() -> None:
    submission = make_submission()
    session = RecordingSession()

    with pytest.raises(GradingOrchestrationError, match="active rubric binding"):
        resolve_grading_context(session, submission=submission)


def test_orchestrate_for_submission_resolves_required_answer_key_version() -> None:
    submission = make_submission()
    rubric = make_rubric_version(submission)
    binding = make_rubric_binding(submission, rubric)
    answer_key = make_answer_key_version(
        submission,
        key_payload={
            "rules": [
                {
                    "criterion_key": "correctness",
                    "rule_type": "accepted_variants",
                    "accepted": ["deterministic checks should run before ai."],
                    "correct_level": "meets",
                    "incorrect_level": "needs_revision",
                }
            ]
        },
    )
    session = RecordingSession(
        scalar_results=[binding, answer_key],
        get_results={(RubricVersion, rubric.id): rubric},
    )

    outcome = orchestrate_grading_for_submission(
        session,
        submission=submission,
        answer_key_required=True,
        selected_levels_by_criterion={"clarity": "meets"},
    )

    assert outcome.grading_run.rubric_version_id == rubric.id
    assert outcome.grading_run.answer_key_version_id == answer_key.id
    assert outcome.grading_run.context_payload["answer_key_selection_source"] == "assessment_item_latest_published"
    assert outcome.grading_result is not None
    assert outcome.grading_result.total_score == Decimal("6")


def test_orchestrate_for_submission_blocks_when_required_answer_key_is_missing() -> None:
    submission = make_submission()
    rubric = make_rubric_version(submission)
    binding = make_rubric_binding(submission, rubric)
    session = RecordingSession(
        scalar_results=[binding, None],
        get_results={(RubricVersion, rubric.id): rubric},
    )

    with pytest.raises(Exception, match="answer key version"):
        orchestrate_grading_for_submission(
            session,
            submission=submission,
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
    deterministic_audit = next(
        event for event in records(session, AuditEvent) if event.action == "grading.deterministic_checks_completed"
    )
    assert deterministic_audit.new_state["selected_levels_by_criterion"] == {
        "correctness": "meets",
        "clarity": "partial",
    }
    assert deterministic_audit.new_state["total_score"] == "5"
    assert deterministic_audit.new_state["max_score"] == "6"


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
                    "evidence_references": evidence_refs(submission),
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
    ai_audit = next(event for event in records(session, AuditEvent) if event.action == "ai_interaction.completed")
    assert ai_audit.new_state["provider"] == "fake"
    assert ai_audit.new_state["model"] == "fake-model"
    assert ai_audit.new_state["validation_status"] == "valid"
    assert ai_audit.new_state["criterion_keys"] == ["correctness"]


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
                    "evidence_references": evidence_refs(submission),
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
                    "evidence_references": evidence_refs(submission),
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
                    "evidence_references": evidence_refs(submission),
                },
                {
                    "criterion_key": "clarity",
                    "score": "2",
                    "confidence": "0.95",
                    "explanation": "Clear and direct.",
                    "evidence_references": evidence_refs(submission),
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


def test_medium_confidence_ai_only_full_coverage_routes_to_review() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    provider = FakeAIProvider(
        {
            "criterion_suggestions": [
                {
                    "criterion_key": "correctness",
                    "score": "4",
                    "confidence": "0.82",
                    "explanation": "Likely correct but not high-confidence.",
                    "evidence_references": evidence_refs(submission),
                },
                {
                    "criterion_key": "clarity",
                    "score": "2",
                    "confidence": "0.82",
                    "explanation": "Clear enough but not high-confidence.",
                    "evidence_references": evidence_refs(submission),
                },
            ],
            "overall_feedback_draft": "Plausible answer.",
            "confidence": "0.82",
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
    assert outcome.review_task is not None
    assert outcome.review_task.confidence_band == "medium"
    assert outcome.review_task.escalation_reason == "confidence_below_threshold"


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


def test_review_routing_reuses_existing_open_review_task_for_result() -> None:
    submission = make_submission()
    rubric = make_rubric_version(submission)
    existing_task = ReviewTask(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        assessment_id=submission.assessment_id,
        assessment_item_id=submission.assessment_item_id,
        submission_id=submission.id,
        grading_run_id=uuid.uuid4(),
        grading_result_id=uuid.uuid4(),
        status="open",
        priority="normal",
        confidence_band="low",
        escalation_reason="old_reason",
        policy_payload={"reasons": ["old_reason"]},
    )
    session = RecordingSession(scalar_results=[existing_task])

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        selected_levels_by_criterion={"correctness": "meets", "clarity": "meets"},
        policy=GradingPolicy(mandatory_review=True),
    )

    assert outcome.review_task is existing_task
    assert existing_task.escalation_reason == "mandatory_review_policy"
    assert existing_task.confidence_band == "high"
    assert existing_task.policy_payload["duplicate_routing_reused"] is True
    assert len(records(session, ReviewTask)) == 0


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
                    "evidence_references": evidence_refs(submission),
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


def test_ai_output_without_evidence_references_routes_to_review() -> None:
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
                    "explanation": "No evidence reference.",
                },
                {
                    "criterion_key": "clarity",
                    "score": "2",
                    "confidence": "0.95",
                    "explanation": "No evidence reference.",
                },
            ],
            "overall_feedback_draft": "Missing evidence links.",
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

    assert outcome.ai_interaction is not None
    assert outcome.ai_interaction.validation_status == "invalid"
    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "needs_review"
    assert outcome.review_task is not None
    assert outcome.review_task.escalation_reason == "ai_validation_failed"
    assert "ai_output.validation_failed" in [event.action for event in records(session, AuditEvent)]
    assert all(record.source != "ai" for record in records(session, CriterionResult))


def test_optional_invalid_ai_does_not_block_complete_deterministic_finalization() -> None:
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
                    "explanation": "Missing evidence references makes this invalid.",
                }
            ],
            "confidence": "0.95",
        }
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        selected_levels_by_criterion={"correctness": "meets", "clarity": "meets"},
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=True, ai_required=False),
    )

    assert outcome.ai_interaction is not None
    assert outcome.ai_interaction.validation_status == "invalid"
    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "finalized"
    assert outcome.review_task is None
    assert "ai_output.validation_failed" in [event.action for event in records(session, AuditEvent)]
    assert outcome.grading_result.explanation_payload["ai_validation_summary"]["validation_status"] == "invalid"


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


def test_answer_key_accepted_variants_selects_deterministic_level_before_ai() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    answer_key = make_answer_key_version(
        submission,
        key_payload={
            "rules": [
                {
                    "criterion_key": "correctness",
                    "rule_type": "accepted_variants",
                    "accepted": ["deterministic checks should run before ai."],
                    "correct_level": "meets",
                    "incorrect_level": "needs_revision",
                }
            ]
        },
    )
    provider = FakeAIProvider(
        {
            "criterion_suggestions": [
                {
                    "criterion_key": "correctness",
                    "score": "0",
                    "confidence": "0.99",
                    "explanation": "Would disagree if called.",
                }
            ],
            "confidence": "0.99",
        }
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        answer_key_version=answer_key,
        answer_key_required=True,
        selected_levels_by_criterion={"clarity": "meets"},
        ai_provider=provider,
        policy=GradingPolicy(ai_allowed=False),
    )

    assert provider.requests == []
    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "finalized"
    assert outcome.grading_result.total_score == Decimal("6")
    correctness = [record for record in records(session, CriterionResult) if record.criterion_key == "correctness"][0]
    assert correctness.score == Decimal("4")
    assert correctness.metadata_payload["answer_key_finding"]["matched"] is True
    assert correctness.metadata_payload["answer_key_finding"]["rule_type"] == "accepted_variants"


def test_answer_key_miss_selects_incorrect_level_and_can_finalize_when_coverage_complete() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    answer_key = make_answer_key_version(
        submission,
        key_payload={
            "rules": [
                {
                    "criterion_key": "correctness",
                    "rule_type": "exact_text",
                    "expected": "A different answer.",
                    "correct_level": "meets",
                    "incorrect_level": "needs_revision",
                }
            ]
        },
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        answer_key_version=answer_key,
        answer_key_required=True,
        selected_levels_by_criterion={"clarity": "meets"},
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "finalized"
    assert outcome.grading_result.total_score == Decimal("2")
    correctness = [record for record in records(session, CriterionResult) if record.criterion_key == "correctness"][0]
    assert correctness.score == Decimal("0")
    assert correctness.metadata_payload["selected_level"] == "needs_revision"
    assert correctness.metadata_payload["answer_key_finding"]["matched"] is False


def test_answer_key_numeric_tolerance_uses_structured_evidence_payload() -> None:
    session = RecordingSession()
    submission = make_submission()
    submission.evidence[0].raw_text = None
    submission.evidence[0].value_payload = {"numeric_answer": "3.14"}
    rubric = make_rubric_version(submission)
    answer_key = make_answer_key_version(
        submission,
        key_payload={
            "rules": [
                {
                    "criterion_key": "correctness",
                    "rule_type": "numeric_tolerance",
                    "evidence_key": "numeric_answer",
                    "expected": "3.10",
                    "tolerance": "0.05",
                    "correct_level": "meets",
                    "incorrect_level": "needs_revision",
                }
            ]
        },
    )

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        answer_key_version=answer_key,
        answer_key_required=True,
        selected_levels_by_criterion={"clarity": "meets"},
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "finalized"
    assert outcome.grading_result.total_score == Decimal("6")
    correctness = [record for record in records(session, CriterionResult) if record.criterion_key == "correctness"][0]
    assert correctness.metadata_payload["answer_key_finding"]["observed_value"] == "3.14"
    assert correctness.metadata_payload["answer_key_finding"]["matched"] is True


def test_answer_key_without_supported_rules_routes_to_review() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    answer_key = make_answer_key_version(submission, key_payload={"notes": "No deterministic rule."})

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        answer_key_version=answer_key,
        answer_key_required=True,
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "needs_review"
    assert outcome.review_task is not None
    assert outcome.review_task.escalation_reason == "partial_grading"
    assert "answer_key_no_rules" in outcome.review_task.policy_payload["reasons"]


def test_answer_key_warning_routes_to_review_even_when_manual_coverage_is_complete() -> None:
    session = RecordingSession()
    submission = make_submission()
    rubric = make_rubric_version(submission)
    answer_key = make_answer_key_version(submission, key_payload={"notes": "No deterministic rule."})

    outcome = orchestrate_grading(
        session,
        submission=submission,
        rubric_version=rubric,
        answer_key_version=answer_key,
        answer_key_required=True,
        selected_levels_by_criterion={"correctness": "meets", "clarity": "meets"},
    )

    assert outcome.grading_result is not None
    assert outcome.grading_result.status == "needs_review"
    assert outcome.review_task is not None
    assert outcome.review_task.escalation_reason == "answer_key_no_rules"
    assert outcome.review_task.confidence_band == "high"
