from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.db.models import CriterionResult, GradingResult, GradingRun, TeacherReview


ELIGIBLE_RESULT_STATUSES = {"finalized"}
ELIGIBLE_RESULT_TYPES = {"reviewed", "overridden", "final"}
REVIEWED_EVALUATION_RESULT_TYPES = {"reviewed", "overridden"}


def is_calibration_candidate(result: GradingResult) -> bool:
    return result.status in ELIGIBLE_RESULT_STATUSES and result.result_type in ELIGIBLE_RESULT_TYPES


def reviewed_example_payload(
    *,
    result: GradingResult,
    grading_run: GradingRun | None = None,
    teacher_review: TeacherReview | None = None,
) -> dict[str, Any]:
    if not is_calibration_candidate(result):
        raise ValueError("Only finalized final/reviewed/overridden results can become reviewed examples.")

    return {
        "grading_result_id": str(result.id) if result.id is not None else None,
        "grading_run_id": str(result.grading_run_id),
        "submission_id": str(grading_run.submission_id) if grading_run is not None else None,
        "rubric_version_id": str(result.rubric_version_id) if result.rubric_version_id is not None else None,
        "answer_key_version_id": str(result.answer_key_version_id) if result.answer_key_version_id else None,
        "result_type": result.result_type,
        "status": result.status,
        "total_score": _decimal_to_string(result.total_score),
        "max_score": _decimal_to_string(result.max_score),
        "confidence": _decimal_to_string(result.confidence),
        "teacher_decision": teacher_review.decision if teacher_review is not None else None,
        "teacher_review_id": str(teacher_review.id) if teacher_review is not None and teacher_review.id else None,
        "metadata": {
            "has_feedback": bool(result.feedback),
            "has_explanation_payload": bool(result.explanation_payload),
        },
    }


def reviewed_result_evaluation_case_payload(
    *,
    result: GradingResult,
    grading_run: GradingRun | None = None,
    teacher_review: TeacherReview | None = None,
    criterion_results: list[CriterionResult] | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    if result.status not in ELIGIBLE_RESULT_STATUSES or result.result_type not in REVIEWED_EVALUATION_RESULT_TYPES:
        raise ValueError("Only finalized reviewed/overridden results can become evaluation calibration cases.")

    criteria = criterion_results
    if criteria is None:
        criteria = list(result.criterion_results or [])

    return {
        "case_id": case_id or f"reviewed_result_{result.id}",
        "grading_result_id": str(result.id) if result.id is not None else None,
        "grading_run_id": str(result.grading_run_id),
        "submission_id": str(grading_run.submission_id) if grading_run is not None else None,
        "rubric_version_id": str(result.rubric_version_id) if result.rubric_version_id is not None else None,
        "answer_key_version_id": str(result.answer_key_version_id) if result.answer_key_version_id else None,
        "expected_outcome": {
            "total_score": _decimal_to_string(result.total_score),
            "max_score": _decimal_to_string(result.max_score),
            "routing": "review",
            "criteria": [_criterion_payload(criterion) for criterion in criteria],
        },
        "metadata": {
            "privacy": "public_safe",
            "calibration_source": "reviewed_result",
            "result_type": result.result_type,
            "teacher_decision": teacher_review.decision if teacher_review is not None else None,
            "teacher_review_id": str(teacher_review.id) if teacher_review is not None and teacher_review.id else None,
            "has_feedback": bool(result.feedback),
            "has_explanation_payload": bool(result.explanation_payload),
        },
    }


def _criterion_payload(criterion: CriterionResult) -> dict[str, str | None]:
    return {
        "criterion_key": criterion.criterion_key,
        "score": _decimal_to_string(criterion.score),
        "max_score": _decimal_to_string(criterion.max_score),
    }


def _decimal_to_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
