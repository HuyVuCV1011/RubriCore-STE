from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Rubric
from app.db.services.rubrics import validate_rubric_schema


class RubricAuthoringError(ValueError):
    """Raised when a rubric draft cannot be edited."""


def update_rubric_draft(
    db: Session,
    *,
    rubric: Rubric,
    draft_schema: dict[str, Any],
    actor_user_id: uuid.UUID | None = None,
    actor_source: str = "teacher",
    title: str | None = None,
    description: str | None = None,
    metadata_patch: dict[str, Any] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> Rubric:
    if rubric.status == "archived":
        raise RubricAuthoringError("Archived rubrics cannot be edited.")

    validate_rubric_schema(draft_schema)
    previous_state = {
        "title": rubric.title,
        "description": rubric.description,
        "status": rubric.status,
        "criteria": [criterion.get("key") for criterion in rubric.draft_schema.get("criteria", [])],
    }

    rubric.title = title if title is not None else rubric.title
    rubric.description = description if description is not None else rubric.description
    rubric.draft_schema = copy.deepcopy(draft_schema)
    rubric.status = "draft"
    if metadata_patch:
        rubric.metadata_payload = {**(rubric.metadata_payload or {}), **copy.deepcopy(metadata_patch)}
    db.flush()

    db.add(
        AuditEvent(
            organization_id=rubric.organization_id,
            actor_user_id=actor_user_id,
            actor_source=actor_source,
            action="rubric.draft_updated",
            entity_type="rubric",
            entity_id=rubric.id,
            request_id=request_id,
            previous_state=previous_state,
            new_state={
                "title": rubric.title,
                "description": rubric.description,
                "status": rubric.status,
                "criteria": [criterion.get("key") for criterion in rubric.draft_schema.get("criteria", [])],
                "metadata_payload": copy.deepcopy(rubric.metadata_payload),
            },
            reason=reason,
        )
    )
    return rubric
