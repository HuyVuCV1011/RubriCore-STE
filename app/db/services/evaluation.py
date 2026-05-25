from __future__ import annotations

from decimal import Decimal
from typing import Any


FINAL_ROUTE = "final"
REVIEW_ROUTE = "review"


def total_score_delta(expected: Any, actual: Any) -> Decimal | None:
    expected_score = _score_value(expected, "total_score")
    actual_score = _score_value(actual, "total_score")
    if expected_score is None or actual_score is None:
        return None
    return actual_score - expected_score


def criterion_score_agreement(expected: Any, actual: Any) -> dict[str, Any]:
    expected_scores = _criterion_scores(expected)
    actual_scores = _criterion_scores(actual)
    common_keys = sorted(expected_scores.keys() & actual_scores.keys())
    matching_keys = [key for key in common_keys if actual_scores[key] == expected_scores[key]]
    deltas = {
        key: actual_scores[key] - expected_scores[key]
        for key in common_keys
        if actual_scores[key] != expected_scores[key]
    }

    return {
        "matching_count": len(matching_keys),
        "compared_count": len(common_keys),
        "expected_count": len(expected_scores),
        "actual_count": len(actual_scores),
        "agreement_rate": Decimal(len(matching_keys)) / Decimal(len(common_keys)) if common_keys else None,
        "matching_criteria": matching_keys,
        "score_deltas": deltas,
        "missing_actual": sorted(expected_scores.keys() - actual_scores.keys()),
        "unexpected_actual": sorted(actual_scores.keys() - expected_scores.keys()),
    }


def final_review_routing_agreement(expected: Any, actual: Any) -> dict[str, Any]:
    expected_route = _routing_value(expected)
    actual_route = _routing_value(actual)
    return {
        "expected_route": expected_route,
        "actual_route": actual_route,
        "agrees": expected_route is not None and actual_route is not None and expected_route == actual_route,
    }


def evaluation_case_report(*, case: dict[str, Any], actual_outcome: Any) -> dict[str, Any]:
    expected_outcome = case.get("expected_outcome")
    if not isinstance(expected_outcome, dict):
        raise ValueError("Evaluation case requires expected_outcome.")

    score_delta = total_score_delta(expected_outcome, actual_outcome)
    criterion_metrics = criterion_score_agreement(expected_outcome, actual_outcome)
    routing_metrics = final_review_routing_agreement(expected_outcome, actual_outcome)
    passed = (
        score_delta == Decimal("0")
        and criterion_metrics["compared_count"]
        == criterion_metrics["expected_count"]
        == criterion_metrics["actual_count"]
        and criterion_metrics["matching_count"] == criterion_metrics["expected_count"]
        and routing_metrics["agrees"] is True
    )

    return {
        "case_id": case.get("case_id"),
        "submission_ref": case.get("submission_ref"),
        "passed": passed,
        "metrics": {
            "total_score_delta": score_delta,
            "criterion_score_agreement": criterion_metrics,
            "routing_agreement": routing_metrics,
        },
    }


def evaluation_dataset_report(
    *,
    manifest: dict[str, Any],
    actual_outcomes_by_case_id: dict[str, Any] | None = None,
    use_expected_as_actual: bool = False,
) -> dict[str, Any]:
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation manifest requires a non-empty cases list.")

    reports: list[dict[str, Any]] = []
    missing_actuals: list[str] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"Evaluation case {index} must be an object.")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"Evaluation case {index} requires case_id.")

        actual_outcome = None
        if actual_outcomes_by_case_id is not None:
            actual_outcome = actual_outcomes_by_case_id.get(case_id)
        elif "actual_outcome" in case:
            actual_outcome = case["actual_outcome"]
        elif use_expected_as_actual:
            actual_outcome = case.get("expected_outcome")

        if actual_outcome is None:
            missing_actuals.append(case_id)
            continue
        reports.append(evaluation_case_report(case=case, actual_outcome=actual_outcome))

    passed_count = sum(1 for report in reports if report["passed"])
    return {
        "fixture_set": manifest.get("fixture_set"),
        "privacy": manifest.get("privacy"),
        "case_count": len(cases),
        "evaluated_count": len(reports),
        "passed_count": passed_count,
        "failed_count": len(reports) - passed_count,
        "missing_actuals": missing_actuals,
        "case_reports": reports,
    }


def json_safe_evaluation_report(report: Any) -> Any:
    if isinstance(report, Decimal):
        return str(report)
    if isinstance(report, dict):
        return {key: json_safe_evaluation_report(value) for key, value in report.items()}
    if isinstance(report, list):
        return [json_safe_evaluation_report(value) for value in report]
    return report


def _criterion_scores(value: Any) -> dict[str, Decimal]:
    criteria = _field(value, "criteria")
    if criteria is None:
        criteria = _field(value, "criterion_results")
    if not isinstance(criteria, list):
        return {}

    scores: dict[str, Decimal] = {}
    for criterion in criteria:
        key = _field(criterion, "criterion_key")
        if key is None:
            key = _field(criterion, "key")
        score = _score_value(criterion, "score")
        if isinstance(key, str) and key.strip() and score is not None:
            scores[key] = score
    return scores


def _routing_value(value: Any) -> str | None:
    explicit_route = _field(value, "routing")
    if explicit_route is None:
        explicit_route = _field(value, "route")
    if explicit_route is None:
        explicit_route = _field(value, "expected_route")
    if isinstance(explicit_route, str):
        normalized = explicit_route.strip().lower()
        if normalized in {FINAL_ROUTE, REVIEW_ROUTE}:
            return normalized

    status = _field(value, "status")
    if status == "finalized":
        return FINAL_ROUTE
    if status == "needs_review":
        return REVIEW_ROUTE
    return None


def _score_value(value: Any, field_name: str) -> Decimal | None:
    raw_value = _field(value, field_name)
    if raw_value is None:
        return None
    return Decimal(str(raw_value))


def _field(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)
