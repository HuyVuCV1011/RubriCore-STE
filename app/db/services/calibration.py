from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.db.models import GradingResult, GradingRun, TeacherReview


ELIGIBLE_RESULT_STATUSES = {"finalized"}
ELIGIBLE_RESULT_TYPES = {"reviewed", "overridden", "final"}


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


def _decimal_to_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
