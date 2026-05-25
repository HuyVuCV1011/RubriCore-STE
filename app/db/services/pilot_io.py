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
    "evaluation_manifest",
    "evaluation_case",
}

PUBLIC_MANIFEST_SENSITIVE_MARKERS = {
    "api_key",
    "confidential",
    "credential",
    "private_prompt",
    "private_rubric",
    "private_school",
    "production_secret",
    "real_learner",
    "real_student",
    "school_name:",
    "secret",
    "student_name:",
}


def validate_fixture_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not manifest.get("fixture_set"):
        errors.append("Manifest requires fixture_set.")
    if not manifest.get("title"):
        errors.append("Manifest requires title.")
    if manifest.get("privacy") != "public_safe":
        errors.append("Committed fixture manifests must use privacy='public_safe'.")
    sensitive_markers = _public_manifest_sensitive_markers(manifest)
    if sensitive_markers:
        marker_list = ", ".join(sorted(sensitive_markers))
        errors.append(f"Public-safe fixture manifest includes sensitive marker(s): {marker_list}.")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("Manifest requires a non-empty files list.")
        return errors

    for index, file_entry in enumerate(files):
        errors.extend(_validate_fixture_file_entry(file_entry, entry_label=f"File entry {index}"))

    source_references = manifest.get("source_references", [])
    if source_references:
        if not isinstance(source_references, list):
            errors.append("Manifest source_references must be a list when provided.")
        else:
            for index, file_entry in enumerate(source_references):
                errors.extend(_validate_fixture_file_entry(file_entry, entry_label=f"Source reference {index}"))
    return errors


def _validate_fixture_file_entry(file_entry: Any, *, entry_label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(file_entry, dict):
        errors.append(f"{entry_label} must be an object.")
        return errors
    path = file_entry.get("path")
    purpose = file_entry.get("purpose")
    if not isinstance(path, str) or not path.strip():
        errors.append(f"{entry_label} requires path.")
    elif not _is_safe_relative_fixture_path(path):
        errors.append(f"{entry_label} path must be relative and stay inside fixture root.")
    if purpose not in KNOWN_FILE_PURPOSES:
        errors.append(f"{entry_label} has unknown purpose {purpose!r}.")
    if not file_entry.get("description"):
        errors.append(f"{entry_label} requires description.")
    return errors


def _is_safe_relative_fixture_path(path: str) -> bool:
    parts = path.split("/")
    return not (
        path.startswith("/")
        or "\\" in path
        or path.startswith("~")
        or any(part in {"", ".", ".."} for part in parts)
        or ":" in parts[0]
    )


def _public_manifest_sensitive_markers(value: Any) -> set[str]:
    markers: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            markers.update(_public_manifest_sensitive_markers(key))
            markers.update(_public_manifest_sensitive_markers(item))
    elif isinstance(value, list):
        for item in value:
            markers.update(_public_manifest_sensitive_markers(item))
    elif isinstance(value, str):
        normalized = value.lower()
        markers.update(marker for marker in PUBLIC_MANIFEST_SENSITIVE_MARKERS if marker in normalized)
    return markers


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
