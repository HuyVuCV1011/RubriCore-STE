from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnswerKey, AnswerKeyVersion, AuditEvent


class AnswerKeyValidationError(ValueError):
    """Raised when an answer-key payload is incomplete or unsafe to publish."""


def validate_answer_key_payload(payload: dict[str, Any]) -> None:
    accepted = payload.get("accepted")
    rules = payload.get("rules")
    if accepted is None and rules is None:
        raise AnswerKeyValidationError("Answer key payload requires accepted values or rules.")
    if accepted is not None and (
        not isinstance(accepted, list) or not accepted or any(value in (None, "") for value in accepted)
    ):
        raise AnswerKeyValidationError("Answer key accepted values must be a non-empty list.")
    if rules is not None:
        if not isinstance(rules, list) or not rules:
            raise AnswerKeyValidationError("Answer key rules must be a non-empty list.")
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("type"), str) or not rule["type"].strip():
                raise AnswerKeyValidationError("Every answer key rule requires a non-empty type.")


def create_answer_key(
    db: Session,
    *,
    organization_id: uuid.UUID,
    assessment_item_id: uuid.UUID,
    title: str,
    draft_key: dict[str, Any],
    created_by_user_id: uuid.UUID | None = None,
) -> AnswerKey:
    validate_answer_key_payload(draft_key)
    answer_key = AnswerKey(
        organization_id=organization_id,
        assessment_item_id=assessment_item_id,
        created_by_user_id=created_by_user_id,
        title=title,
        status="draft",
        draft_key=copy.deepcopy(draft_key),
    )
    db.add(answer_key)
    db.flush()
    return answer_key


def update_answer_key_draft(db: Session, *, answer_key: AnswerKey, draft_key: dict[str, Any]) -> AnswerKey:
    if answer_key.status == "archived":
        raise AnswerKeyValidationError("Archived answer keys cannot be edited.")
    validate_answer_key_payload(draft_key)
    answer_key.draft_key = copy.deepcopy(draft_key)
    answer_key.status = "draft"
    db.flush()
    return answer_key


def publish_answer_key_version(
    db: Session,
    *,
    answer_key: AnswerKey,
    published_by_user_id: uuid.UUID | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> AnswerKeyVersion:
    validate_answer_key_payload(answer_key.draft_key)
    next_version = (answer_key.latest_version_number or 0) + 1
    version = AnswerKeyVersion(
        organization_id=answer_key.organization_id,
        answer_key_id=answer_key.id,
        version_number=next_version,
        key_payload=copy.deepcopy(answer_key.draft_key),
        published_by_user_id=published_by_user_id,
        status="published",
    )
    db.add(version)
    db.flush()
    previous_state = {
        "status": answer_key.status,
        "latest_version_number": answer_key.latest_version_number,
    }
    answer_key.status = "published"
    answer_key.latest_version_number = next_version
    db.flush()
    db.add(
        AuditEvent(
            organization_id=answer_key.organization_id,
            actor_user_id=published_by_user_id,
            actor_source="teacher",
            action="answer_key_version.published",
            entity_type="answer_key_version",
            entity_id=version.id,
            request_id=request_id,
            previous_state=previous_state,
            new_state={
                "answer_key_id": str(answer_key.id),
                "answer_key_version_id": str(version.id),
                "version_number": version.version_number,
                "status": version.status,
            },
            reason=reason,
        )
    )
    return version
