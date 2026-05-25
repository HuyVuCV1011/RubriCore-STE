from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.db.models import GradingResult


KNOWN_FILE_PURPOSES = {
    "assessment_material",
    "answer_key_source",
    "submission_evidence",
    "reference_solution",
    "extracted_representation",
    "rubric_source",
    "knowledge_source",
    "converted_markdown",
}


def validate_fixture_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not manifest.get("fixture_set"):
        errors.append("Manifest requires fixture_set.")
    if not manifest.get("title"):
        errors.append("Manifest requires title.")
    if manifest.get("privacy") != "public_safe":
        errors.append("Committed fixture manifests must use privacy='public_safe'.")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("Manifest requires a non-empty files list.")
        return errors

    for index, file_entry in enumerate(files):
        if not isinstance(file_entry, dict):
            errors.append(f"File entry {index} must be an object.")
            continue
        path = file_entry.get("path")
        purpose = file_entry.get("purpose")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"File entry {index} requires path.")
        elif path.startswith("/") or ".." in path.split("/"):
            errors.append(f"File entry {index} path must be relative and stay inside fixture root.")
        if purpose not in KNOWN_FILE_PURPOSES:
            errors.append(f"File entry {index} has unknown purpose {purpose!r}.")
        if not file_entry.get("description"):
            errors.append(f"File entry {index} requires description.")
    return errors


def export_grading_result(result: GradingResult) -> dict[str, Any]:
    return {
        "grading_result_id": str(result.id) if result.id is not None else None,
        "grading_run_id": str(result.grading_run_id),
        "rubric_version_id": str(result.rubric_version_id) if result.rubric_version_id else None,
        "answer_key_version_id": str(result.answer_key_version_id) if result.answer_key_version_id else None,
        "result_type": result.result_type,
        "status": result.status,
        "total_score": _decimal_to_string(result.total_score),
        "max_score": _decimal_to_string(result.max_score),
        "confidence": _decimal_to_string(result.confidence),
        "feedback": result.feedback,
        "explanation_payload": result.explanation_payload,
    }


def _decimal_to_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
