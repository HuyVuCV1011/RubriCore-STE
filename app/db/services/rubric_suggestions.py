from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Rubric, RubricSuggestion
from app.db.services.rubrics import validate_rubric_schema


VALID_SUGGESTION_TYPES = {"criterion", "descriptor", "feedback_theme", "accepted_variant", "rubric_note"}


class RubricSuggestionError(ValueError):
    """Raised when a rubric suggestion cannot move through its lifecycle."""


def create_rubric_suggestion(
    db: Session,
    *,
    organization_id: uuid.UUID,
    target_rubric_id: uuid.UUID,
    suggestion_type: str,
    suggestion_payload: dict[str, Any],
    source_citations: list[dict[str, Any]],
    target_assessment_id: uuid.UUID | None = None,
    target_assessment_item_id: uuid.UUID | None = None,
    created_by_user_id: uuid.UUID | None = None,
    metadata_payload: dict[str, Any] | None = None,
    actor_source: str = "knowledge_library",
    reason: str | None = None,
    request_id: str | None = None,
) -> RubricSuggestion:
    if suggestion_type not in VALID_SUGGESTION_TYPES:
        raise RubricSuggestionError(f"Unsupported rubric suggestion type: {suggestion_type}.")
    if not source_citations:
        raise RubricSuggestionError("Rubric suggestions require at least one source citation.")
    if not suggestion_payload:
        raise RubricSuggestionError("Rubric suggestions require a payload.")

    suggestion = RubricSuggestion(
        organization_id=organization_id,
        target_rubric_id=target_rubric_id,
        target_assessment_id=target_assessment_id,
        target_assessment_item_id=target_assessment_item_id,
        suggestion_type=suggestion_type,
        status="draft",
        created_by_user_id=created_by_user_id,
        suggestion_payload=copy.deepcopy(suggestion_payload),
        source_citations=copy.deepcopy(source_citations),
        metadata_payload=metadata_payload or {},
    )
    db.add(suggestion)
    db.flush()

    _audit_suggestion_event(
        db,
        organization_id=organization_id,
        actor_user_id=created_by_user_id,
        actor_source=actor_source,
        action="rubric_suggestion.created",
        entity_type="rubric_suggestion",
        entity_id=suggestion.id,
        previous_state={},
        new_state={
            "rubric_suggestion_id": str(suggestion.id),
            "target_rubric_id": str(target_rubric_id),
            "suggestion_type": suggestion_type,
            "status": suggestion.status,
            "citation_count": len(source_citations),
        },
        reason=reason,
        request_id=request_id,
    )
    return suggestion


def reject_rubric_suggestion(
    db: Session,
    *,
    suggestion: RubricSuggestion,
    reviewed_by_user_id: uuid.UUID,
    reason: str,
    actor_source: str = "teacher",
    request_id: str | None = None,
) -> RubricSuggestion:
    _require_draft_suggestion(suggestion)
    if not reason.strip():
        raise RubricSuggestionError("Rejecting a rubric suggestion requires a reason.")

    previous_state = _suggestion_state(suggestion)
    suggestion.status = "rejected"
    suggestion.reviewed_by_user_id = reviewed_by_user_id
    suggestion.decision_reason = reason
    db.flush()

    _audit_suggestion_event(
        db,
        organization_id=suggestion.organization_id,
        actor_user_id=reviewed_by_user_id,
        actor_source=actor_source,
        action="rubric_suggestion.rejected",
        entity_type="rubric_suggestion",
        entity_id=suggestion.id,
        previous_state=previous_state,
        new_state=_suggestion_state(suggestion),
        reason=reason,
        request_id=request_id,
    )
    return suggestion


def accept_rubric_suggestion(
    db: Session,
    *,
    suggestion: RubricSuggestion,
    reviewed_by_user_id: uuid.UUID,
    reason: str,
    edited_payload: dict[str, Any] | None = None,
    actor_source: str = "teacher",
    request_id: str | None = None,
) -> RubricSuggestion:
    _require_draft_suggestion(suggestion)
    if not reason.strip():
        raise RubricSuggestionError("Accepting a rubric suggestion requires a reason.")

    rubric = db.get(Rubric, suggestion.target_rubric_id)
    if rubric is None or rubric.organization_id != suggestion.organization_id:
        raise RubricSuggestionError("Rubric suggestion target rubric was not found.")
    if rubric.status == "archived":
        raise RubricSuggestionError("Archived rubrics cannot accept suggestions.")

    accepted_payload = copy.deepcopy(edited_payload or suggestion.suggestion_payload)
    previous_suggestion_state = _suggestion_state(suggestion)
    previous_rubric_state = {
        "status": rubric.status,
        "draft_schema": copy.deepcopy(rubric.draft_schema),
        "metadata_payload": copy.deepcopy(rubric.metadata_payload),
    }
    updated_schema = _apply_suggestion_to_draft_schema(
        rubric.draft_schema,
        suggestion_type=suggestion.suggestion_type,
        payload=accepted_payload,
        source_citations=suggestion.source_citations,
        suggestion_id=suggestion.id,
    )
    validate_rubric_schema(updated_schema)

    rubric.draft_schema = updated_schema
    rubric.status = "draft"
    rubric.metadata_payload = {
        **(rubric.metadata_payload or {}),
        "has_unpublished_knowledge_suggestions": True,
    }
    suggestion.status = "accepted"
    suggestion.reviewed_by_user_id = reviewed_by_user_id
    suggestion.accepted_payload = accepted_payload
    suggestion.decision_reason = reason
    db.flush()

    _audit_suggestion_event(
        db,
        organization_id=suggestion.organization_id,
        actor_user_id=reviewed_by_user_id,
        actor_source=actor_source,
        action="rubric_suggestion.accepted",
        entity_type="rubric_suggestion",
        entity_id=suggestion.id,
        previous_state=previous_suggestion_state,
        new_state=_suggestion_state(suggestion),
        reason=reason,
        request_id=request_id,
    )
    _audit_suggestion_event(
        db,
        organization_id=rubric.organization_id,
        actor_user_id=reviewed_by_user_id,
        actor_source=actor_source,
        action="rubric.draft_updated_from_suggestion",
        entity_type="rubric",
        entity_id=rubric.id,
        previous_state=previous_rubric_state,
        new_state={
            "status": rubric.status,
            "suggestion_id": str(suggestion.id),
            "criterion_keys": [criterion["key"] for criterion in rubric.draft_schema.get("criteria", [])],
        },
        reason=reason,
        request_id=request_id,
    )
    return suggestion


def supersede_rubric_suggestion(
    db: Session,
    *,
    suggestion: RubricSuggestion,
    actor_user_id: uuid.UUID | None = None,
    reason: str | None = None,
    actor_source: str = "system",
    request_id: str | None = None,
) -> RubricSuggestion:
    _require_draft_suggestion(suggestion)
    previous_state = _suggestion_state(suggestion)
    suggestion.status = "superseded"
    suggestion.decision_reason = reason
    db.flush()
    _audit_suggestion_event(
        db,
        organization_id=suggestion.organization_id,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action="rubric_suggestion.superseded",
        entity_type="rubric_suggestion",
        entity_id=suggestion.id,
        previous_state=previous_state,
        new_state=_suggestion_state(suggestion),
        reason=reason,
        request_id=request_id,
    )
    return suggestion


def _apply_suggestion_to_draft_schema(
    draft_schema: dict[str, Any],
    *,
    suggestion_type: str,
    payload: dict[str, Any],
    source_citations: list[dict[str, Any]],
    suggestion_id: uuid.UUID | None,
) -> dict[str, Any]:
    updated = copy.deepcopy(draft_schema)
    if suggestion_type == "criterion":
        criterion = copy.deepcopy(payload.get("criterion", payload))
        descriptors = copy.deepcopy(payload.get("descriptors", []))
        _append_criterion(updated, criterion, descriptors, source_citations, suggestion_id)
        return updated
    if suggestion_type == "descriptor":
        descriptor = copy.deepcopy(payload.get("descriptor", payload))
        _append_descriptor(updated, descriptor, source_citations, suggestion_id)
        return updated

    metadata = updated.setdefault("metadata_payload", {})
    metadata.setdefault("accepted_knowledge_suggestions", []).append(
        {
            "suggestion_id": str(suggestion_id) if suggestion_id is not None else None,
            "suggestion_type": suggestion_type,
            "payload": copy.deepcopy(payload),
            "source_citations": copy.deepcopy(source_citations),
        }
    )
    return updated


def _append_criterion(
    draft_schema: dict[str, Any],
    criterion: dict[str, Any],
    descriptors: list[dict[str, Any]],
    source_citations: list[dict[str, Any]],
    suggestion_id: uuid.UUID | None,
) -> None:
    criteria = draft_schema.setdefault("criteria", [])
    key = criterion.get("key")
    if not isinstance(key, str) or not key.strip():
        raise RubricSuggestionError("Criterion suggestions require a non-empty criterion key.")
    if any(existing.get("key") == key for existing in criteria):
        raise RubricSuggestionError(f"Criterion {key!r} already exists; use an explicit edit workflow.")

    next_position = max((item.get("position", -1) for item in criteria), default=-1) + 1
    criterion.setdefault("position", next_position)
    criterion.setdefault("metadata_payload", {})
    criterion["metadata_payload"] = {
        **criterion["metadata_payload"],
        "knowledge_suggestion_id": str(suggestion_id) if suggestion_id is not None else None,
        "source_citations": copy.deepcopy(source_citations),
    }
    criteria.append(criterion)

    for descriptor in descriptors:
        descriptor.setdefault("criterion_key", key)
        _append_descriptor(draft_schema, descriptor, source_citations, suggestion_id)


def _append_descriptor(
    draft_schema: dict[str, Any],
    descriptor: dict[str, Any],
    source_citations: list[dict[str, Any]],
    suggestion_id: uuid.UUID | None,
) -> None:
    descriptors = draft_schema.setdefault("descriptors", [])
    criterion_key = descriptor.get("criterion_key")
    performance_level_key = descriptor.get("performance_level_key")
    if any(
        existing.get("criterion_key") == criterion_key
        and existing.get("performance_level_key") == performance_level_key
        for existing in descriptors
    ):
        raise RubricSuggestionError(
            f"Descriptor {criterion_key!r}/{performance_level_key!r} already exists; use an explicit edit workflow."
        )
    descriptor.setdefault("metadata_payload", {})
    descriptor["metadata_payload"] = {
        **descriptor["metadata_payload"],
        "knowledge_suggestion_id": str(suggestion_id) if suggestion_id is not None else None,
        "source_citations": copy.deepcopy(source_citations),
    }
    descriptors.append(descriptor)


def _require_draft_suggestion(suggestion: RubricSuggestion) -> None:
    if suggestion.status != "draft":
        raise RubricSuggestionError("Only draft rubric suggestions can receive this action.")


def _suggestion_state(suggestion: RubricSuggestion) -> dict[str, Any]:
    return {
        "status": suggestion.status,
        "reviewed_by_user_id": str(suggestion.reviewed_by_user_id) if suggestion.reviewed_by_user_id else None,
        "decision_reason": suggestion.decision_reason,
        "accepted_payload": copy.deepcopy(suggestion.accepted_payload),
    }


def _audit_suggestion_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    actor_source: str,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    reason: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=request_id,
        previous_state=copy.deepcopy(previous_state),
        new_state=copy.deepcopy(new_state),
        reason=reason,
    )
    db.add(event)
    return event
