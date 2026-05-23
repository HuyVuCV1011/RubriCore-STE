from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select

from app.db.models import (
    AIInteraction,
    AuditEvent,
    CriterionResult,
    GradingResult,
    GradingRun,
    ReviewTask,
    Submission,
)
from app.db.models.rubric import AnswerKey, AnswerKeyVersion, RubricBinding, RubricVersion
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

ROUTING_AUTO_ACCEPT = "auto_accept"
ROUTING_REVIEW = "route_to_review"
ROUTING_FAIL_RUN = "fail_run"
ROUTING_RETRY_AI_STEP = "retry_ai_step"

REASON_AUTO_FINALIZE_POLICY_PASSED = "auto_finalize_policy_passed"
REASON_CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"
REASON_CONFIDENCE_MISSING = "confidence_missing"
REASON_DETERMINISTIC_AI_DISAGREEMENT = "deterministic_ai_disagreement"
REASON_SCORE_DISAGREEMENT = "score_disagreement"
REASON_AI_VALIDATION_FAILED = "ai_validation_failed"
REASON_MANDATORY_REVIEW_POLICY = "mandatory_review_policy"
REASON_PARTIAL_GRADING = "partial_grading"
REASON_RUBRIC_COVERAGE_INCOMPLETE = "rubric_coverage_incomplete"
REASON_AUTO_FINALIZE_DISABLED = "auto_finalize_disabled"
REASON_ANSWER_KEY_NO_RULES = "answer_key_no_rules"


class GradingOrchestrationError(ValueError):
    """Raised when grading orchestration cannot safely continue."""


class AIOutputValidationError(GradingOrchestrationError):
    """Raised when AI output does not satisfy the grading output contract."""


class GradingSession(Protocol):
    def add(self, record: object) -> None: ...

    def flush(self) -> None: ...

    def get(self, entity: object, ident: object) -> object | None: ...

    def scalar(self, statement: object) -> object | None: ...


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


@dataclass(frozen=True)
class ConfidencePolicyDecision:
    decision: str
    confidence: Decimal | None
    confidence_band: str
    reasons: list[str]
    review_priority: str
    retryable: bool
    reviewer_summary: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ResolvedGradingContext:
    rubric_version: RubricVersion
    answer_key_version: AnswerKeyVersion | None
    context_payload: dict[str, Any]


def resolve_grading_context(
    db: GradingSession,
    *,
    submission: Submission,
    rubric_version: RubricVersion | None = None,
    answer_key_version: AnswerKeyVersion | None = None,
    answer_key_required: bool = False,
) -> ResolvedGradingContext:
    resolved_rubric = rubric_version
    rubric_binding: RubricBinding | None = None
    rubric_selection_source = "explicit" if rubric_version is not None else None

    if resolved_rubric is None:
        rubric_binding, rubric_selection_source = _resolve_active_rubric_binding(db, submission=submission)
        if rubric_binding is not None:
            resolved_rubric = _rubric_version_from_binding(db, rubric_binding)

    if resolved_rubric is None:
        raise GradingOrchestrationError(
            "A published rubric version or active rubric binding is required before grading."
        )
    _validate_published_rubric_version(submission, resolved_rubric)

    resolved_answer_key = answer_key_version
    answer_key_selection_source = "explicit" if answer_key_version is not None else None
    if resolved_answer_key is None and answer_key_required:
        resolved_answer_key = _resolve_latest_published_answer_key_version(db, submission=submission)
        answer_key_selection_source = "assessment_item_latest_published" if resolved_answer_key is not None else None

    if answer_key_required or resolved_answer_key is not None:
        _validate_published_answer_key_version(submission, resolved_answer_key)

    return ResolvedGradingContext(
        rubric_version=resolved_rubric,
        answer_key_version=resolved_answer_key,
        context_payload={
            "rubric_selection_source": rubric_selection_source,
            "rubric_binding_id": str(rubric_binding.id) if rubric_binding is not None else None,
            "answer_key_selection_source": answer_key_selection_source,
        },
    )


def orchestrate_grading_for_submission(
    db: GradingSession,
    *,
    submission: Submission,
    rubric_version: RubricVersion | None = None,
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
    resolved_context = resolve_grading_context(
        db,
        submission=submission,
        rubric_version=rubric_version,
        answer_key_version=answer_key_version,
        answer_key_required=answer_key_required,
    )
    merged_context_payload = {
        **copy.deepcopy(context_payload or {}),
        **copy.deepcopy(resolved_context.context_payload),
    }
    return orchestrate_grading(
        db,
        submission=submission,
        rubric_version=resolved_context.rubric_version,
        answer_key_version=resolved_context.answer_key_version,
        selected_levels_by_criterion=selected_levels_by_criterion,
        ai_provider=ai_provider,
        answer_key_required=answer_key_required,
        policy=policy,
        triggered_by_user_id=triggered_by_user_id,
        trigger_source=trigger_source,
        reason=reason,
        request_id=request_id,
        context_payload=merged_context_payload,
    )


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
            submission=submission,
            rubric_version=rubric_version,
            answer_key_version=answer_key_version,
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
    submission: Submission,
    rubric_version: RubricVersion,
    answer_key_version: AnswerKeyVersion | None,
    selected_levels_by_criterion: dict[str, str],
) -> dict[str, Any]:
    required_criterion_keys = [criterion["key"] for criterion in rubric_version.rubric_schema.get("criteria", [])]
    answer_key_payload = _run_answer_key_checks(
        submission=submission,
        rubric_version=rubric_version,
        answer_key_version=answer_key_version,
    )
    deterministic_levels = {
        **answer_key_payload["selected_levels_by_criterion"],
        **copy.deepcopy(selected_levels_by_criterion),
    }
    warnings = list(answer_key_payload["warnings"])
    if not deterministic_levels:
        return {
            "selected_levels_by_criterion": {},
            "criterion_scores": {},
            "total_score": None,
            "max_score": _max_score_from_rubric(rubric_version),
            "confidence": Decimal("0"),
            "confidence_band": CONFIDENCE_BLOCKED,
            "required_criterion_keys": required_criterion_keys,
            "answer_key_findings": answer_key_payload["findings"],
            "warnings": _dedupe([*warnings, REASON_PARTIAL_GRADING]),
        }
    summary = calculate_deterministic_score(rubric_version.rubric_schema, deterministic_levels)
    return {
        "selected_levels_by_criterion": copy.deepcopy(deterministic_levels),
        "criterion_scores": summary.criterion_scores,
        "total_score": summary.total_score,
        "max_score": summary.max_score,
        "confidence": Decimal("1"),
        "confidence_band": CONFIDENCE_HIGH,
        "required_criterion_keys": required_criterion_keys,
        "answer_key_findings": answer_key_payload["findings"],
        "manual_selected_levels_by_criterion": copy.deepcopy(selected_levels_by_criterion),
        "warnings": warnings,
    }


def _run_answer_key_checks(
    *,
    submission: Submission,
    rubric_version: RubricVersion,
    answer_key_version: AnswerKeyVersion | None,
) -> dict[str, Any]:
    if answer_key_version is None:
        return {"selected_levels_by_criterion": {}, "findings": [], "warnings": []}

    rules = _answer_key_rules(answer_key_version, rubric_version)
    if not rules:
        return {
            "selected_levels_by_criterion": {},
            "findings": [],
            "warnings": [REASON_ANSWER_KEY_NO_RULES],
        }

    selected_levels: dict[str, str] = {}
    findings: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        finding = _evaluate_answer_key_rule(
            submission=submission,
            answer_key_version=answer_key_version,
            rule=rule,
            rule_index=index,
        )
        findings.append(finding)
        selected_levels[finding["criterion_key"]] = finding["selected_level"]
    return {"selected_levels_by_criterion": selected_levels, "findings": findings, "warnings": []}


def _answer_key_rules(answer_key_version: AnswerKeyVersion, rubric_version: RubricVersion) -> list[dict[str, Any]]:
    payload = answer_key_version.key_payload or {}
    criteria = rubric_version.rubric_schema.get("criteria", [])
    default_criterion_key = criteria[0]["key"] if criteria else None
    if isinstance(payload.get("rules"), list):
        return [
            _normalize_answer_key_rule(rule, default_criterion_key=default_criterion_key)
            for rule in payload["rules"]
            if isinstance(rule, dict)
        ]
    if isinstance(payload.get("criteria"), dict):
        return [
            _normalize_answer_key_rule({**rule, "criterion_key": criterion_key}, default_criterion_key=criterion_key)
            for criterion_key, rule in payload["criteria"].items()
            if isinstance(rule, dict)
        ]
    if any(key in payload for key in ("accepted", "accepted_variants", "expected", "pattern")):
        return [_normalize_answer_key_rule(payload, default_criterion_key=default_criterion_key)]
    return []


def _normalize_answer_key_rule(rule: dict[str, Any], *, default_criterion_key: str | None) -> dict[str, Any]:
    normalized = copy.deepcopy(rule)
    normalized.setdefault("criterion_key", default_criterion_key)
    normalized.setdefault("rule_type", normalized.get("type") or _infer_answer_key_rule_type(normalized))
    normalized.setdefault("correct_level", normalized.get("level_on_match") or "meets")
    normalized.setdefault("incorrect_level", normalized.get("level_on_miss") or "needs_revision")
    return normalized


def _infer_answer_key_rule_type(rule: dict[str, Any]) -> str:
    if "pattern" in rule:
        return "regex"
    if "tolerance" in rule:
        return "numeric_tolerance"
    if "numeric_value" in rule:
        return "numeric_exact"
    if "accepted_variants" in rule or "accepted" in rule:
        return "accepted_variants"
    return "exact_text"


def _evaluate_answer_key_rule(
    *,
    submission: Submission,
    answer_key_version: AnswerKeyVersion,
    rule: dict[str, Any],
    rule_index: int,
) -> dict[str, Any]:
    criterion_key = rule.get("criterion_key")
    if not isinstance(criterion_key, str) or not criterion_key.strip():
        raise GradingOrchestrationError("Answer key rule requires a criterion_key.")

    observed_value = _answer_key_observed_value(submission, rule, criterion_key)
    rule_type = str(rule.get("rule_type"))
    matched = _answer_key_rule_matches(rule_type=rule_type, rule=rule, observed_value=observed_value)
    selected_level = str(rule["correct_level"] if matched else rule["incorrect_level"])
    return {
        "answer_key_version_id": str(answer_key_version.id),
        "rule_index": rule_index,
        "criterion_key": criterion_key,
        "rule_type": rule_type,
        "observed_value": observed_value,
        "matched": matched,
        "selected_level": selected_level,
        "explanation": _answer_key_explanation(rule_type=rule_type, matched=matched),
    }


def _answer_key_observed_value(submission: Submission, rule: dict[str, Any], criterion_key: str) -> str | None:
    evidence_key = rule.get("evidence_key")
    for evidence in submission.evidence:
        value_payload = evidence.value_payload or {}
        if isinstance(evidence_key, str) and evidence_key in value_payload:
            return str(value_payload[evidence_key])
        if criterion_key in value_payload:
            return str(value_payload[criterion_key])
        if "answer" in value_payload:
            return str(value_payload["answer"])
        if evidence.raw_text is not None and evidence.raw_text.strip():
            return evidence.raw_text
    return None


def _answer_key_rule_matches(*, rule_type: str, rule: dict[str, Any], observed_value: str | None) -> bool:
    if observed_value is None:
        return False
    if rule_type == "exact_text":
        return observed_value == str(rule.get("expected", ""))
    if rule_type == "normalized_text":
        return _normalize_text(observed_value) == _normalize_text(str(rule.get("expected", "")))
    if rule_type == "accepted_variants":
        accepted_values = rule.get("accepted_variants", rule.get("accepted", []))
        if not isinstance(accepted_values, list):
            accepted_values = [accepted_values]
        return _normalize_text(observed_value) in {_normalize_text(str(value)) for value in accepted_values}
    if rule_type == "numeric_exact":
        return _decimal_or_none(observed_value) == _decimal_or_none(rule.get("numeric_value", rule.get("expected")))
    if rule_type == "numeric_tolerance":
        observed_decimal = _decimal_or_none(observed_value)
        expected_decimal = _decimal_or_none(rule.get("numeric_value", rule.get("expected")))
        tolerance = _decimal_or_none(rule.get("tolerance"))
        if observed_decimal is None or expected_decimal is None or tolerance is None:
            return False
        return abs(observed_decimal - expected_decimal) <= tolerance
    if rule_type == "regex":
        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return False
        return re.search(pattern, observed_value) is not None
    raise GradingOrchestrationError(f"Unsupported answer key rule type {rule_type!r}.")


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _decimal_or_none(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _answer_key_explanation(*, rule_type: str, matched: bool) -> str:
    state = "matched" if matched else "did not match"
    return f"Answer key {rule_type} rule {state} submitted evidence."


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
    confidence_band = _confidence_band(confidence, policy=policy)
    coverage_summary = _rubric_coverage_summary(rubric_version, deterministic_payload, ai_payload)
    ai_validation_summary = _ai_validation_summary(ai_payload, ai_validation_error)
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
            "confidence_summary": {
                "policy_confidence": str(confidence) if confidence is not None else None,
                "confidence_band": confidence_band,
                "source_confidences": _json_safe(_source_confidences(deterministic_payload, ai_payload)),
                "calculation": _confidence_calculation_label(deterministic_payload, ai_payload),
            },
            "ai_validation_summary": ai_validation_summary,
            "rubric_coverage_summary": coverage_summary,
            "disagreement_flags": _disagreement_flags(deterministic_payload, ai_payload),
            "review_reasons": [],
            "policy": {
                "grading_policy_version": policy.grading_policy_version,
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
    decision = _evaluate_confidence_policy(
        grading_result=grading_result,
        deterministic_payload=deterministic_payload,
        ai_payload=ai_payload,
        ai_validation_error=ai_validation_error,
        policy=policy,
    )
    if decision.decision == ROUTING_AUTO_ACCEPT:
        grading_result.status = GRADING_RESULT_FINALIZED
        grading_result.result_type = "final"
        _merge_confidence_policy_payload(grading_result, decision)
        _audit_grading_event(
            db,
            submission=submission,
            grading_run=grading_run,
            action="grading_result.auto_finalized",
            actor_user_id=grading_run.triggered_by_user_id,
            actor_source=grading_run.trigger_source,
            previous_state={"status": GRADING_RESULT_PROPOSED},
            new_state={"status": grading_result.status, "grading_result_id": str(grading_result.id)},
            reason=REASON_AUTO_FINALIZE_POLICY_PASSED,
            request_id=grading_run.context_payload.get("request_id"),
        )
        return None

    grading_result.status = GRADING_RESULT_NEEDS_REVIEW
    _merge_confidence_policy_payload(grading_result, decision)
    review_task = ReviewTask(
        organization_id=submission.organization_id,
        assessment_id=submission.assessment_id,
        assessment_item_id=submission.assessment_item_id,
        submission_id=submission.id,
        grading_run_id=grading_run.id,
        grading_result_id=grading_result.id,
        status="open",
        priority=decision.review_priority,
        confidence_band=decision.confidence_band,
        escalation_reason=decision.reasons[0],
        policy_payload={
            **copy.deepcopy(decision.payload),
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
            "confidence_band": decision.confidence_band,
            "escalation_reason": review_task.escalation_reason,
            "reasons": decision.reasons,
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
    answer_key_findings = {
        finding["criterion_key"]: finding for finding in deterministic_payload.get("answer_key_findings", [])
    }
    criterion_max_scores = _criterion_max_scores(rubric_version)
    for criterion_key, score in deterministic_scores.items():
        answer_key_finding = answer_key_findings.get(criterion_key)
        record = CriterionResult(
            organization_id=submission.organization_id,
            grading_result_id=grading_result.id,
            criterion_key=criterion_key,
            source="deterministic",
            score=score,
            max_score=criterion_max_scores[criterion_key],
            confidence=Decimal("1"),
            explanation=_deterministic_explanation(criterion_key, selected_levels, answer_key_finding),
            metadata_payload={
                "selected_level": selected_levels.get(criterion_key),
                "rubric_version_id": str(rubric_version.id),
                "answer_key_finding": copy.deepcopy(answer_key_finding) if answer_key_finding is not None else None,
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


def _deterministic_explanation(
    criterion_key: str,
    selected_levels: dict[str, str],
    answer_key_finding: dict[str, Any] | None,
) -> str:
    if answer_key_finding is not None:
        return str(answer_key_finding["explanation"])
    return f"Deterministic rubric level {selected_levels.get(criterion_key)!r} selected."


def _evaluate_confidence_policy(
    *,
    grading_result: GradingResult,
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
    ai_validation_error: str | None,
    policy: GradingPolicy,
) -> ConfidencePolicyDecision:
    reasons: list[str] = []
    if policy.mandatory_review:
        reasons.append(REASON_MANDATORY_REVIEW_POLICY)
    if ai_validation_error is not None:
        reasons.append(REASON_AI_VALIDATION_FAILED)
    if policy.ai_required and ai_payload is None:
        reasons.append(REASON_AI_VALIDATION_FAILED)
    coverage_summary = _coverage_summary_from_payloads(deterministic_payload, ai_payload)
    if not coverage_summary["coverage_complete"]:
        reasons.append(REASON_PARTIAL_GRADING)
        reasons.append(REASON_RUBRIC_COVERAGE_INCOMPLETE)
    if _has_deterministic_ai_disagreement(deterministic_payload, ai_payload):
        reasons.append(REASON_DETERMINISTIC_AI_DISAGREEMENT)
    if not policy.auto_finalize_allowed:
        reasons.append(REASON_AUTO_FINALIZE_DISABLED)
    if grading_result.confidence is None:
        reasons.append(REASON_CONFIDENCE_MISSING)
    elif grading_result.confidence < policy.confidence_threshold:
        reasons.append(REASON_CONFIDENCE_BELOW_THRESHOLD)
    if deterministic_payload.get("warnings") and not coverage_summary["coverage_complete"]:
        reasons.extend(deterministic_payload["warnings"])

    reasons = _dedupe(reasons)
    confidence_band = _confidence_band(grading_result.confidence, policy=policy)
    routing_decision = ROUTING_AUTO_ACCEPT if not reasons else ROUTING_REVIEW
    payload = {
        "decision": routing_decision,
        "confidence": str(grading_result.confidence) if grading_result.confidence is not None else None,
        "confidence_band": confidence_band,
        "reasons": reasons,
        "policy_version": policy.grading_policy_version,
        "thresholds": {
            "confidence_threshold": str(policy.confidence_threshold),
            "review_threshold": str(policy.review_threshold),
        },
        "review_priority": _review_priority(reasons),
        "retryable": False,
        "reviewer_summary": _reviewer_summary(routing_decision, reasons, confidence_band),
        "contributing_signals": {
            "source_confidences": _json_safe(_source_confidences(deterministic_payload, ai_payload)),
            "calculation": _confidence_calculation_label(deterministic_payload, ai_payload),
        },
        "blocking_signals": reasons,
        "rubric_coverage_summary": coverage_summary,
        "ai_validation_summary": _ai_validation_summary(ai_payload, ai_validation_error),
        "disagreement_flags": _disagreement_flags(deterministic_payload, ai_payload),
        "auto_finalize_allowed": policy.auto_finalize_allowed,
    }
    return ConfidencePolicyDecision(
        decision=routing_decision,
        confidence=grading_result.confidence,
        confidence_band=confidence_band,
        reasons=reasons,
        review_priority=_review_priority(reasons),
        retryable=False,
        reviewer_summary=payload["reviewer_summary"],
        payload=payload,
    )


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


def _source_confidences(
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
) -> dict[str, Decimal | None]:
    confidences: dict[str, Decimal | None] = {}
    if deterministic_payload.get("criterion_scores"):
        confidences["deterministic"] = Decimal(str(deterministic_payload.get("confidence", Decimal("1"))))
    if ai_payload is not None:
        confidences["ai"] = Decimal(str(ai_payload["confidence"]))
    return confidences


def _confidence_calculation_label(
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
) -> str:
    if deterministic_payload.get("criterion_scores") and ai_payload is not None:
        return "minimum_valid_contributing_confidence"
    if deterministic_payload.get("criterion_scores"):
        return "deterministic_confidence"
    if ai_payload is not None:
        return "validated_ai_aggregate_confidence"
    return "blocked_no_scoring_signal"


def _coverage_summary_from_payloads(
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    required_keys = set(deterministic_payload.get("required_criterion_keys", []))
    deterministic_keys = set(deterministic_payload.get("criterion_scores", {}))
    ai_keys = (
        {suggestion["criterion_key"] for suggestion in ai_payload.get("criterion_suggestions", [])}
        if ai_payload is not None
        else set()
    )
    covered_keys = deterministic_keys | ai_keys
    missing_keys = required_keys - covered_keys
    return {
        "required_criterion_keys": sorted(required_keys),
        "deterministic_criterion_keys": sorted(deterministic_keys),
        "ai_criterion_keys": sorted(ai_keys),
        "covered_criterion_keys": sorted(covered_keys),
        "missing_criterion_keys": sorted(missing_keys),
        "coverage_complete": not missing_keys and bool(required_keys),
    }


def _rubric_coverage_summary(
    rubric_version: RubricVersion,
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = copy.deepcopy(deterministic_payload)
    payload["required_criterion_keys"] = [
        criterion["key"] for criterion in rubric_version.rubric_schema.get("criteria", [])
    ]
    return _coverage_summary_from_payloads(payload, ai_payload)


def _ai_validation_summary(
    ai_payload: dict[str, Any] | None,
    ai_validation_error: str | None,
) -> dict[str, Any]:
    if ai_payload is not None:
        return {
            "validation_status": "valid",
            "confidence": ai_payload.get("confidence"),
            "criterion_count": len(ai_payload.get("criterion_suggestions", [])),
            "error": None,
        }
    if ai_validation_error is not None:
        return {
            "validation_status": "invalid",
            "confidence": None,
            "criterion_count": 0,
            "error": ai_validation_error,
        }
    return {
        "validation_status": "not_used",
        "confidence": None,
        "criterion_count": 0,
        "error": None,
    }


def _disagreement_flags(
    deterministic_payload: dict[str, Any],
    ai_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if ai_payload is None:
        return {"has_disagreement": False, "criterion_disagreements": []}
    deterministic_scores: dict[str, Decimal] = deterministic_payload.get("criterion_scores", {})
    disagreements: list[dict[str, str]] = []
    for suggestion in ai_payload["criterion_suggestions"]:
        criterion_key = suggestion["criterion_key"]
        if criterion_key not in deterministic_scores:
            continue
        deterministic_score = deterministic_scores[criterion_key]
        ai_score = Decimal(str(suggestion["score"]))
        if ai_score != deterministic_score:
            disagreements.append(
                {
                    "criterion_key": criterion_key,
                    "deterministic_score": str(deterministic_score),
                    "ai_score": str(ai_score),
                }
            )
    return {
        "has_disagreement": bool(disagreements),
        "criterion_disagreements": disagreements,
    }


def _merge_confidence_policy_payload(
    grading_result: GradingResult,
    decision: ConfidencePolicyDecision,
) -> None:
    grading_result.explanation_payload["confidence_summary"] = {
        **grading_result.explanation_payload.get("confidence_summary", {}),
        "policy_confidence": str(decision.confidence) if decision.confidence is not None else None,
        "confidence_band": decision.confidence_band,
    }
    grading_result.explanation_payload["routing"] = {
        "decision": decision.decision,
        "confidence_band": decision.confidence_band,
        "reasons": decision.reasons,
        "reviewer_summary": decision.reviewer_summary,
        "retryable": decision.retryable,
    }
    grading_result.explanation_payload["review_reasons"] = decision.reasons
    grading_result.explanation_payload["contributing_signals"] = copy.deepcopy(
        decision.payload.get("contributing_signals", {})
    )
    grading_result.explanation_payload["blocking_signals"] = copy.deepcopy(decision.payload.get("blocking_signals", []))


def _reviewer_summary(decision: str, reasons: list[str], confidence_band: str) -> str:
    if decision == ROUTING_AUTO_ACCEPT:
        return "Result met confidence, completeness, disagreement, and policy gates for auto-finalization."
    if not reasons:
        return f"Result routed to review with confidence band {confidence_band}."
    reason = reasons[0]
    summaries = {
        REASON_MANDATORY_REVIEW_POLICY: "Policy requires teacher review regardless of confidence.",
        REASON_AUTO_FINALIZE_DISABLED: "Auto-finalization is disabled by policy.",
        REASON_AI_VALIDATION_FAILED: "AI output failed validation and cannot be used as authoritative scoring input.",
        REASON_PARTIAL_GRADING: "The candidate result does not cover every required rubric criterion.",
        REASON_RUBRIC_COVERAGE_INCOMPLETE: "Rubric coverage is incomplete.",
        REASON_DETERMINISTIC_AI_DISAGREEMENT: "Deterministic and AI scoring signals disagree.",
        REASON_CONFIDENCE_BELOW_THRESHOLD: "Aggregate confidence is below the auto-finalization threshold.",
        REASON_CONFIDENCE_MISSING: "Aggregate confidence is missing.",
    }
    return summaries.get(reason, f"Result requires teacher review because of {reason}.")


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


def _resolve_active_rubric_binding(
    db: GradingSession,
    *,
    submission: Submission,
) -> tuple[RubricBinding | None, str | None]:
    if submission.assessment_item_id is not None:
        binding = db.scalar(
            select(RubricBinding)
            .where(
                RubricBinding.organization_id == submission.organization_id,
                RubricBinding.assessment_item_id == submission.assessment_item_id,
                RubricBinding.status == "active",
            )
            .order_by(RubricBinding.created_at.desc())
        )
        if binding is not None:
            return _typed_rubric_binding(binding), "assessment_item_binding"

    if submission.assessment_id is not None:
        binding = db.scalar(
            select(RubricBinding)
            .where(
                RubricBinding.organization_id == submission.organization_id,
                RubricBinding.assessment_id == submission.assessment_id,
                RubricBinding.status == "active",
            )
            .order_by(RubricBinding.created_at.desc())
        )
        if binding is not None:
            return _typed_rubric_binding(binding), "assessment_binding"

    return None, None


def _rubric_version_from_binding(db: GradingSession, binding: RubricBinding) -> RubricVersion:
    if binding.rubric_version is not None:
        return binding.rubric_version
    rubric_version = db.get(RubricVersion, binding.rubric_version_id)
    if rubric_version is None:
        raise GradingOrchestrationError("Active rubric binding points to a missing rubric version.")
    return _typed_rubric_version(rubric_version)


def _resolve_latest_published_answer_key_version(
    db: GradingSession,
    *,
    submission: Submission,
) -> AnswerKeyVersion | None:
    if submission.assessment_item_id is None:
        return None
    answer_key_version = db.scalar(
        select(AnswerKeyVersion)
        .join(AnswerKey)
        .where(
            AnswerKey.organization_id == submission.organization_id,
            AnswerKey.assessment_item_id == submission.assessment_item_id,
            AnswerKey.status == "published",
            AnswerKeyVersion.organization_id == submission.organization_id,
            AnswerKeyVersion.status == "published",
        )
        .order_by(AnswerKeyVersion.version_number.desc())
    )
    if answer_key_version is None:
        return None
    return _typed_answer_key_version(answer_key_version)


def _typed_rubric_binding(value: object) -> RubricBinding:
    if not isinstance(value, RubricBinding):
        raise GradingOrchestrationError("Rubric binding query returned an unexpected record type.")
    return value


def _typed_rubric_version(value: object) -> RubricVersion:
    if not isinstance(value, RubricVersion):
        raise GradingOrchestrationError("Rubric version lookup returned an unexpected record type.")
    return value


def _typed_answer_key_version(value: object) -> AnswerKeyVersion:
    if not isinstance(value, AnswerKeyVersion):
        raise GradingOrchestrationError("Answer key version query returned an unexpected record type.")
    return value


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


def _confidence_band(confidence: Decimal | None, *, policy: GradingPolicy | None = None) -> str:
    policy = policy or GradingPolicy()
    if confidence is None:
        return CONFIDENCE_BLOCKED
    if confidence >= policy.confidence_threshold:
        return CONFIDENCE_HIGH
    if confidence >= policy.review_threshold:
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
