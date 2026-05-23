from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.db.models import (
    AIInteraction,
    AuditEvent,
    CriterionResult,
    GradingResult,
    GradingRun,
    ReviewTask,
    Submission,
)
from app.db.models.rubric import AnswerKeyVersion, RubricVersion
from app.db.services.answer_lifecycle import SubmissionIntakeError, validate_submission_ready_for_grading
from app.db.services.rubrics import RubricValidationError, calculate_deterministic_score


GRADING_RUN_QUEUED = "queued"
GRADING_RUN_RUNNING = "running"
GRADING_RUN_COMPLETED = "completed"
GRADING_RUN_FAILED = "failed"

GRADING_RESULT_PROPOSED = "proposed"
GRADING_RESULT_NEEDS_REVIEW = "needs_review"
GRADING_RESULT_FINALIZED = "finalized"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_BLOCKED = "blocked"

REASON_CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"
REASON_DETERMINISTIC_AI_DISAGREEMENT = "deterministic_ai_disagreement"
REASON_AI_VALIDATION_FAILED = "ai_validation_failed"
REASON_MANDATORY_REVIEW_POLICY = "mandatory_review_policy"
REASON_PARTIAL_GRADING = "partial_grading"


class GradingOrchestrationError(ValueError):
    """Raised when grading orchestration cannot safely continue."""


class AIOutputValidationError(GradingOrchestrationError):
    """Raised when AI output does not satisfy the grading output contract."""


class GradingSession(Protocol):
    def add(self, record: object) -> None: ...

    def flush(self) -> None: ...


class AIGradingProvider(Protocol):
    provider_name: str
    model_name: str

    def evaluate(self, request_payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class GradingPolicy:
    confidence_threshold: Decimal = Decimal("0.85")
    review_threshold: Decimal = Decimal("0.70")
    ai_allowed: bool = False
    ai_required: bool = False
    auto_finalize_allowed: bool = True
    mandatory_review: bool = False
    grading_policy_version: str | None = "phase-1-default"
    prompt_version: str | None = "phase-1-short-answer-v1"
    ai_output_schema_version: str | None = "phase-1-grading-output-v1"


@dataclass(frozen=True)
class OrchestrationResult:
    grading_run: GradingRun
    grading_result: GradingResult | None
    review_task: ReviewTask | None
    ai_interaction: AIInteraction | None


def start_grading_run(
    db: GradingSession,
    *,
    submission: Submission,
    rubric_version: RubricVersion,
    answer_key_version: AnswerKeyVersion | None = None,
    answer_key_required: bool = False,
    policy: GradingPolicy | None = None,
    triggered_by_user_id: UUID | None = None,
    trigger_source: str = "system",
    reason: str | None = None,
    request_id: str | None = None,
    context_payload: dict[str, Any] | None = None,
) -> GradingRun:
    policy = policy or GradingPolicy()
    _validate_published_rubric_version(submission, rubric_version)
    if answer_key_required or answer_key_version is not None:
        _validate_published_answer_key_version(submission, answer_key_version)
    validate_submission_ready_for_grading(
        submission,
        rubric_version_id=rubric_version.id,
        answer_key_version_id=answer_key_version.id if answer_key_version is not None else None,
        answer_key_required=answer_key_required,
    )

    payload = copy.deepcopy(context_payload) if context_payload is not None else {}
    payload.update(
        {
            "reason": reason,
            "request_id": request_id,
            "ai_allowed": policy.ai_allowed,
            "ai_required": policy.ai_required,
            "auto_finalize_allowed": policy.auto_finalize_allowed,
            "mandatory_review": policy.mandatory_review,
            "confidence_threshold": str(policy.confidence_threshold),
            "review_threshold": str(policy.review_threshold),
        }
    )
    run = GradingRun(
        organization_id=submission.organization_id,
        submission_id=submission.id,
        rubric_version_id=rubric_version.id,
        answer_key_version_id=answer_key_version.id if answer_key_version is not None else None,
        triggered_by_user_id=triggered_by_user_id,
        trigger_source=trigger_source,
        status=GRADING_RUN_QUEUED,
        grading_policy_version=policy.grading_policy_version,
        context_payload=payload,
    )
    db.add(run)
    db.flush()
    _audit_grading_event(
        db,
        submission=submission,
        grading_run=run,
        action="grading_run.created",
        actor_user_id=triggered_by_user_id,
        actor_source=trigger_source,
        previous_state={},
        new_state=_grading_run_state(run),
        reason=reason,
        request_id=request_id,
    )
    db.flush()
    return run


def orchestrate_grading(
    db: GradingSession,
    *,
    submission: Submission,
    rubric_version: RubricVersion,
    answer_key_version: AnswerKeyVersion | None = None,
    selected_levels_by_criterion: dict[str, str] | None = None,
    ai_provider: AIGradingProvider | None = None,
    answer_key_required: bool = False,
    policy: GradingPolicy | None = None,
    triggered_by_user_id: UUID | None = None,
    trigger_source: str = "system",
    reason: str | None = None,
    request_id: str | None = None,
    context_payload: dict[str, Any] | None = None,
) -> OrchestrationResult:
    policy = policy or GradingPolicy()
    run = start_grading_run(
        db,
        submission=submission,
        rubric_version=rubric_version,
        answer_key_version=answer_key_version,
        answer_key_required=answer_key_required,
        policy=policy,
        triggered_by_user_id=triggered_by_user_id,
        trigger_source=trigger_source,
        reason=reason,
        request_id=request_id,
        context_payload=context_payload,
    )
    return execute_grading_run(
        db,
        grading_run=run,
        submission=submission,
        rubric_version=rubric_version,
        answer_key_version=answer_key_version,
        selected_levels_by_criterion=selected_levels_by_criterion,
        ai_provider=ai_provider,
        policy=policy,
        actor_user_id=triggered_by_user_id,
        actor_source=trigger_source,
        request_id=request_id,
    )


def execute_grading_run(
    db: GradingSession,
    *,
    grading_run: GradingRun,
    submission: Submission,
    rubric_version: RubricVersion,
    answer_key_version: AnswerKeyVersion | None = None,
    selected_levels_by_criterion: dict[str, str] | None = None,
    ai_provider: AIGradingProvider | None = None,
    policy: GradingPolicy | None = None,
    actor_user_id: UUID | None = None,
    actor_source: str = "system",
    request_id: str | None = None,
) -> OrchestrationResult:
    policy = policy or GradingPolicy()
    previous_run_state = _grading_run_state(grading_run)
    grading_run.status = GRADING_RUN_RUNNING
    _audit_grading_event(
        db,
        submission=submission,
        grading_run=grading_run,
        action="grading_run.started",
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        previous_state=previous_run_state,
        new_state=_grading_run_state(grading_run),
        request_id=request_id,
    )

    ai_interaction: AIInteraction | None = None
    try:
        deterministic_payload = _run_deterministic_stage(
            rubric_version=rubric_version,
            selected_levels_by_criterion=selected_levels_by_criterion or {},
        )
        _audit_grading_event(
            db,
            submission=submission,
            grading_run=grading_run,
            action="grading.deterministic_checks_completed",
            actor_user_id=actor_user_id,
            actor_source=actor_source,
            previous_state={},
            new_state={"criterion_keys": sorted(deterministic_payload["criterion_scores"])},
            request_id=request_id,
        )

        ai_payload: dict[str, Any] | None = None
        ai_validation_error: str | None = None
        if policy.ai_allowed and ai_provider is not None:
            ai_interaction, ai_payload, ai_validation_error = _invoke_and_validate_ai(
                db,
                submission=submission,
                grading_run=grading_run,
                rubric_version=rubric_version,
                answer_key_version=answer_key_version,
                deterministic_payload=deterministic_payload,
                ai_provider=ai_provider,
                policy=policy,
            )

        result = _build_grading_result(
            db,
            submission=submission,
            grading_run=grading_run,
            rubric_version=rubric_version,
            answer_key_version=answer_key_version,
            deterministic_payload=deterministic_payload,
            ai_payload=ai_payload,
            ai_validation_error=ai_validation_error,
            policy=policy,
        )
        review_task = _apply_routing_policy(
            db,
            submission=submission,
            grading_run=grading_run,
            grading_result=result,
            deterministic_payload=deterministic_payload,
            ai_payload=ai_payload,
            ai_validation_error=ai_validation_error,
            policy=policy,
        )

        previous_run_state = _grading_run_state(grading_run)
        grading_run.status = GRADING_RUN_COMPLETED
        _audit_grading_event(
            db,
            submission=submission,
            grading_run=grading_run,
            action="grading_run.completed",
            actor_user_id=actor_user_id,
            actor_source=actor_source,
            previous_state=previous_run_state,
            new_state=_grading_run_state(grading_run),
            request_id=request_id,
        )
        db.flush()
        return OrchestrationResult(
            grading_run=grading_run,
            grading_result=result,
            review_task=review_task,
            ai_interaction=ai_interaction,
        )
    except Exception as exc:
        previous_run_state = _grading_run_state(grading_run)
        grading_run.status = GRADING_RUN_FAILED
        _audit_grading_event(
            db,
            submission=submission,
            grading_run=grading_run,
            action="grading_run.failed",
            actor_user_id=actor_user_id,
            actor_source=actor_source,
            previous_state=previous_run_state,
            new_state={"status": grading_run.status, "error": _safe_error(exc)},
            request_id=request_id,
        )
        db.flush()
        raise


def validate_ai_output(ai_output: dict[str, Any], *, rubric_version: RubricVersion) -> dict[str, Any]:
    if not isinstance(ai_output, dict):
        raise AIOutputValidationError("AI output must be an object.")

    suggestions = ai_output.get("criterion_suggestions")
    if not isinstance(suggestions, list) or not suggestions:
        raise AIOutputValidationError("AI output must include criterion_suggestions.")

    criterion_keys = {criterion["key"] for criterion in rubric_version.rubric_schema.get("criteria", [])}
    criterion_max_scores = _criterion_max_scores(rubric_version)

    normalized_suggestions: list[dict[str, Any]] = []
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            raise AIOutputValidationError("Every AI criterion suggestion must be an object.")
        criterion_key = suggestion.get("criterion_key")
        if criterion_key not in criterion_keys:
            raise AIOutputValidationError(f"AI output references unknown criterion {criterion_key!r}.")
        max_score = criterion_max_scores[criterion_key]
        score = _decimal_between(
            suggestion.get("score"),
            lower=Decimal("0"),
            upper=max_score,
            label=f"AI score for {criterion_key}",
        )
        confidence = _confidence_decimal(suggestion.get("confidence"), f"AI confidence for {criterion_key}")
        explanation = suggestion.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            raise AIOutputValidationError(f"AI suggestion for {criterion_key!r} requires an explanation.")
        normalized = copy.deepcopy(suggestion)
        normalized["score"] = str(score)
        normalized["max_score"] = str(max_score)
        normalized["confidence"] = str(confidence)
        normalized_suggestions.append(normalized)

    confidence = _confidence_decimal(ai_output.get("confidence"), "AI aggregate confidence")
    normalized_output = copy.deepcopy(ai_output)
    normalized_output["criterion_suggestions"] = normalized_suggestions
    normalized_output["confidence"] = str(confidence)
    normalized_output.setdefault("overall_feedback_draft", "")
    normalized_output.setdefault("uncertainty_reasons", [])
    normalized_output.setdefault("evidence_references", [])
    normalized_output.setdefault("policy_flags", [])
    return normalized_output


def _run_deterministic_stage(
    *,
    rubric_version: RubricVersion,
    selected_levels_by_criterion: dict[str, str],
) -> dict[str, Any]:
    if not selected_levels_by_criterion:
        return {
            "criterion_scores": {},
            "total_score": None,
            "max_score": _max_score_from_rubric(rubric_version),
            "confidence": Decimal("0"),
            "confidence_band": CONFIDENCE_BLOCKED,
            "warnings": [REASON_PARTIAL_GRADING],
        }
    summary = calculate_deterministic_score(rubric_version.rubric_schema, selected_levels_by_criterion)
    return {
        "selected_levels_by_criterion": copy.deepcopy(selected_levels_by_criterion),
        "criterion_scores": summary.criterion_scores,
        "total_score": summary.total_score,
        "max_score": summary.max_score,
        "confidence": Decimal("1"),
        "confidence_band": CONFIDENCE_HIGH,
        "warnings": [],
    }


def _invoke_and_validate_ai(
    db: GradingSession,
    *,
    submission: Submission,
    grading_run: GradingRun,
    rubric_version: RubricVersion,
    answer_key_version: AnswerKeyVersion | None,
    deterministic_payload: dict[str, Any],
    ai_provider: AIGradingProvider,
    policy: GradingPolicy,
) -> tuple[AIInteraction, dict[str, Any] | None, str | None]:
    request_payload = {
        "submission_id": str(submission.id),
        "rubric_version_id": str(rubric_version.id),
        "answer_key_version_id": str(answer_key_version.id) if answer_key_version is not None else None,
        "rubric_schema": copy.deepcopy(rubric_version.rubric_schema),
        "evidence": _submission_evidence_payload(submission),
        "deterministic": _json_safe(deterministic_payload),
        "output_schema_version": policy.ai_output_schema_version,
    }
    interaction = AIInteraction(
        organization_id=submission.organization_id,
        grading_run_id=grading_run.id,
        provider=ai_provider.provider_name,
        model=ai_provider.model_name,
        prompt_version=policy.prompt_version,
        output_schema_version=policy.ai_output_schema_version,
        validation_status="pending",
        request_metadata=request_payload,
        response_payload={},
        provider_metadata={},
    )
    db.add(interaction)
    db.flush()
    try:
        raw_output = ai_provider.evaluate(request_payload)
        interaction.response_payload = copy.deepcopy(raw_output)
        validated = validate_ai_output(raw_output, rubric_version=rubric_version)
        interaction.validation_status = "valid"
        return interaction, validated, None
    except AIOutputValidationError as exc:
        interaction.validation_status = "invalid"
        interaction.error_message = str(exc)
        return interaction, None, str(exc)
    except Exception as exc:
        interaction.validation_status = "failed"
        interaction.error_message = _safe_error(exc)
        return interaction, None, _safe_error(exc)


def _build_grading_result(
    db: GradingSession,
    *,
    submission: Submission,
    grading_run: GradingRun,
    rubric_version: RubricVersion,
    answer_key_version: AnswerKeyVersion | None,
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
    ai_validation_error: str | None,
    policy: GradingPolicy,
) -> GradingResult:
    total_score, max_score, confidence = _score_and_confidence(deterministic_payload, ai_payload)
    result = GradingResult(
        organization_id=submission.organization_id,
        grading_run_id=grading_run.id,
        rubric_version_id=rubric_version.id,
        answer_key_version_id=answer_key_version.id if answer_key_version is not None else None,
        result_type=GRADING_RESULT_PROPOSED,
        status=GRADING_RESULT_PROPOSED,
        total_score=total_score,
        max_score=max_score,
        confidence=confidence,
        feedback=ai_payload.get("overall_feedback_draft") if ai_payload is not None else None,
        explanation_payload={
            "deterministic": _json_safe(deterministic_payload),
            "ai_validation_error": ai_validation_error,
            "policy": {
                "confidence_threshold": str(policy.confidence_threshold),
                "review_threshold": str(policy.review_threshold),
                "ai_allowed": policy.ai_allowed,
                "ai_required": policy.ai_required,
                "auto_finalize_allowed": policy.auto_finalize_allowed,
                "mandatory_review": policy.mandatory_review,
            },
        },
    )
    db.add(result)
    db.flush()
    _add_criterion_results(
        db,
        submission=submission,
        grading_result=result,
        rubric_version=rubric_version,
        deterministic_payload=deterministic_payload,
        ai_payload=ai_payload,
    )
    db.flush()
    return result


def _apply_routing_policy(
    db: GradingSession,
    *,
    submission: Submission,
    grading_run: GradingRun,
    grading_result: GradingResult,
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
    ai_validation_error: str | None,
    policy: GradingPolicy,
) -> ReviewTask | None:
    reasons = _routing_reasons(
        grading_result=grading_result,
        deterministic_payload=deterministic_payload,
        ai_payload=ai_payload,
        ai_validation_error=ai_validation_error,
        policy=policy,
    )
    confidence_band = _confidence_band(grading_result.confidence)
    if not reasons:
        grading_result.status = GRADING_RESULT_FINALIZED
        grading_result.result_type = "final"
        grading_result.explanation_payload["routing"] = {
            "decision": "auto_finalized",
            "confidence_band": confidence_band,
            "reasons": [],
        }
        _audit_grading_event(
            db,
            submission=submission,
            grading_run=grading_run,
            action="grading_result.auto_finalized",
            actor_user_id=grading_run.triggered_by_user_id,
            actor_source=grading_run.trigger_source,
            previous_state={"status": GRADING_RESULT_PROPOSED},
            new_state={"status": grading_result.status, "grading_result_id": str(grading_result.id)},
            reason="auto_finalize_policy_passed",
            request_id=grading_run.context_payload.get("request_id"),
        )
        return None

    grading_result.status = GRADING_RESULT_NEEDS_REVIEW
    grading_result.explanation_payload["routing"] = {
        "decision": "review",
        "confidence_band": confidence_band,
        "reasons": reasons,
    }
    review_task = ReviewTask(
        organization_id=submission.organization_id,
        assessment_id=submission.assessment_id,
        assessment_item_id=submission.assessment_item_id,
        submission_id=submission.id,
        grading_run_id=grading_run.id,
        grading_result_id=grading_result.id,
        status="open",
        priority=_review_priority(reasons),
        confidence_band=confidence_band,
        escalation_reason=reasons[0],
        policy_payload={
            "reasons": reasons,
            "grading_policy_version": policy.grading_policy_version,
        },
    )
    db.add(review_task)
    _audit_grading_event(
        db,
        submission=submission,
        grading_run=grading_run,
        action="review_task.created",
        actor_user_id=grading_run.triggered_by_user_id,
        actor_source=grading_run.trigger_source,
        previous_state={},
        new_state={
            "grading_result_id": str(grading_result.id),
            "confidence_band": confidence_band,
            "escalation_reason": review_task.escalation_reason,
        },
        reason=review_task.escalation_reason,
        request_id=grading_run.context_payload.get("request_id"),
    )
    return review_task


def _add_criterion_results(
    db: GradingSession,
    *,
    submission: Submission,
    grading_result: GradingResult,
    rubric_version: RubricVersion,
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
) -> None:
    deterministic_scores: dict[str, Decimal] = deterministic_payload.get("criterion_scores", {})
    selected_levels = deterministic_payload.get("selected_levels_by_criterion", {})
    criterion_max_scores = _criterion_max_scores(rubric_version)
    for criterion_key, score in deterministic_scores.items():
        record = CriterionResult(
            organization_id=submission.organization_id,
            grading_result_id=grading_result.id,
            criterion_key=criterion_key,
            source="deterministic",
            score=score,
            max_score=criterion_max_scores[criterion_key],
            confidence=Decimal("1"),
            explanation=f"Deterministic rubric level {selected_levels.get(criterion_key)!r} selected.",
            metadata_payload={
                "selected_level": selected_levels.get(criterion_key),
                "rubric_version_id": str(rubric_version.id),
            },
        )
        db.add(record)

    if ai_payload is None:
        return
    deterministic_keys = set(deterministic_scores)
    for suggestion in ai_payload["criterion_suggestions"]:
        criterion_key = suggestion["criterion_key"]
        if criterion_key in deterministic_keys:
            continue
        record = CriterionResult(
            organization_id=submission.organization_id,
            grading_result_id=grading_result.id,
            criterion_key=criterion_key,
            source="ai",
            score=Decimal(str(suggestion["score"])),
            max_score=Decimal(str(suggestion["max_score"])),
            confidence=Decimal(str(suggestion["confidence"])),
            explanation=suggestion["explanation"],
            metadata_payload={
                "rubric_version_id": str(rubric_version.id),
                "evidence_references": suggestion.get("evidence_references", []),
                "ambiguity_flags": suggestion.get("ambiguity_flags", []),
            },
        )
        db.add(record)


def _routing_reasons(
    *,
    grading_result: GradingResult,
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
    ai_validation_error: str | None,
    policy: GradingPolicy,
) -> list[str]:
    reasons: list[str] = []
    if policy.mandatory_review:
        reasons.append(REASON_MANDATORY_REVIEW_POLICY)
    if ai_validation_error is not None:
        reasons.append(REASON_AI_VALIDATION_FAILED)
    if policy.ai_required and ai_payload is None:
        reasons.append(REASON_AI_VALIDATION_FAILED)
    if deterministic_payload.get("warnings"):
        reasons.extend(deterministic_payload["warnings"])
    if _has_deterministic_ai_disagreement(deterministic_payload, ai_payload):
        reasons.append(REASON_DETERMINISTIC_AI_DISAGREEMENT)
    if not policy.auto_finalize_allowed:
        reasons.append(REASON_MANDATORY_REVIEW_POLICY)
    if grading_result.confidence is None or grading_result.confidence < policy.confidence_threshold:
        reasons.append(REASON_CONFIDENCE_BELOW_THRESHOLD)
    return _dedupe(reasons)


def _has_deterministic_ai_disagreement(
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
) -> bool:
    if ai_payload is None:
        return False
    deterministic_scores: dict[str, Decimal] = deterministic_payload.get("criterion_scores", {})
    if not deterministic_scores:
        return False
    for suggestion in ai_payload["criterion_suggestions"]:
        criterion_key = suggestion["criterion_key"]
        ai_score = Decimal(str(suggestion["score"]))
        if criterion_key in deterministic_scores and ai_score != deterministic_scores[criterion_key]:
            return True
    return False


def _score_and_confidence(
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    deterministic_total = deterministic_payload.get("total_score")
    deterministic_max = deterministic_payload.get("max_score")
    if deterministic_total is not None:
        confidence = Decimal(str(deterministic_payload.get("confidence", Decimal("1"))))
        if ai_payload is not None:
            ai_confidence = Decimal(str(ai_payload["confidence"]))
            confidence = min(confidence, ai_confidence)
        return deterministic_total, deterministic_max, confidence

    if ai_payload is None:
        return None, deterministic_max, Decimal("0")

    total_score = sum((Decimal(str(item["score"])) for item in ai_payload["criterion_suggestions"]), Decimal("0"))
    max_score = sum((Decimal(str(item["max_score"])) for item in ai_payload["criterion_suggestions"]), Decimal("0"))
    return total_score, max_score, Decimal(str(ai_payload["confidence"]))


def _validate_published_rubric_version(submission: Submission, rubric_version: RubricVersion) -> None:
    if rubric_version.id is None:
        raise GradingOrchestrationError("A persisted rubric version is required before grading.")
    if rubric_version.status != "published":
        raise GradingOrchestrationError("Grading requires a published rubric version.")
    if rubric_version.organization_id != submission.organization_id:
        raise GradingOrchestrationError("Rubric version organization must match the submission organization.")
    try:
        calculate_deterministic_score(rubric_version.rubric_schema, {})
    except RubricValidationError:
        raise
    except Exception as exc:
        raise GradingOrchestrationError(f"Rubric schema cannot be loaded: {_safe_error(exc)}") from exc


def _validate_published_answer_key_version(
    submission: Submission,
    answer_key_version: AnswerKeyVersion | None,
) -> None:
    if answer_key_version is None:
        raise SubmissionIntakeError("An answer key version is required for deterministic answer-key grading.")
    if answer_key_version.id is None:
        raise GradingOrchestrationError("A persisted answer key version is required before grading.")
    if answer_key_version.status != "published":
        raise GradingOrchestrationError("Grading requires a published answer key version when an answer key is used.")
    if answer_key_version.organization_id != submission.organization_id:
        raise GradingOrchestrationError("Answer key version organization must match the submission organization.")


def _max_score_from_rubric(rubric_version: RubricVersion) -> Decimal:
    return sum(_criterion_max_scores(rubric_version).values(), Decimal("0"))


def _max_level_score(rubric_version: RubricVersion) -> Decimal:
    return max(
        (Decimal(str(level["score"])) for level in rubric_version.rubric_schema.get("performance_levels", [])),
        default=Decimal("0"),
    )


def _criterion_max_scores(rubric_version: RubricVersion) -> dict[str, Decimal]:
    max_level_score = _max_level_score(rubric_version)
    return {
        criterion["key"]: max_level_score * Decimal(str(criterion.get("weight", 1)))
        for criterion in rubric_version.rubric_schema.get("criteria", [])
    }


def _decimal_between(value: Any, *, lower: Decimal, upper: Decimal, label: str) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except Exception as exc:
        raise AIOutputValidationError(f"{label} must be numeric.") from exc
    if decimal < lower or decimal > upper:
        raise AIOutputValidationError(f"{label} must be between {lower} and {upper}.")
    return decimal


def _confidence_decimal(value: Any, label: str) -> Decimal:
    return _decimal_between(value, lower=Decimal("0"), upper=Decimal("1"), label=label)


def _confidence_band(confidence: Decimal | None) -> str:
    if confidence is None:
        return CONFIDENCE_BLOCKED
    if confidence >= Decimal("0.85"):
        return CONFIDENCE_HIGH
    if confidence >= Decimal("0.70"):
        return CONFIDENCE_MEDIUM
    if confidence > Decimal("0"):
        return CONFIDENCE_LOW
    return CONFIDENCE_BLOCKED


def _review_priority(reasons: list[str]) -> str:
    if REASON_DETERMINISTIC_AI_DISAGREEMENT in reasons or REASON_AI_VALIDATION_FAILED in reasons:
        return "high"
    return "normal"


def _submission_evidence_payload(submission: Submission) -> list[dict[str, Any]]:
    return [
        {
            "id": str(evidence.id),
            "raw_text": evidence.raw_text,
            "value_payload": copy.deepcopy(evidence.value_payload),
            "file_artifact_id": str(evidence.file_artifact_id) if evidence.file_artifact_id is not None else None,
            "evidence_extraction_id": (
                str(evidence.evidence_extraction_id) if evidence.evidence_extraction_id is not None else None
            ),
        }
        for evidence in submission.evidence
    ]


def _audit_grading_event(
    db: GradingSession,
    *,
    submission: Submission,
    grading_run: GradingRun,
    action: str,
    actor_user_id: UUID | None,
    actor_source: str,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    reason: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=submission.organization_id,
        assessment_id=submission.assessment_id,
        submission_id=submission.id,
        grading_run_id=grading_run.id,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action=action,
        entity_type="grading_run",
        entity_id=grading_run.id,
        request_id=request_id,
        previous_state=copy.deepcopy(previous_state),
        new_state=copy.deepcopy(new_state),
        reason=reason,
    )
    db.add(event)
    return event


def _grading_run_state(run: GradingRun) -> dict[str, Any]:
    return {
        "id": str(run.id) if run.id is not None else None,
        "status": run.status,
        "submission_id": str(run.submission_id) if run.submission_id is not None else None,
        "rubric_version_id": str(run.rubric_version_id) if run.rubric_version_id is not None else None,
        "answer_key_version_id": str(run.answer_key_version_id) if run.answer_key_version_id is not None else None,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _safe_error(exc: BaseException) -> str:
    return str(exc) or exc.__class__.__name__


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
