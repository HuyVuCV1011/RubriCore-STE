from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SubjectPack


TAXONOMY_LIST_KEYS = {"assessment_types", "evidence_types", "output_types", "rubric_types"}


class SubjectPackValidationError(ValueError):
    """Raised when a subject-pack config is not pilot-safe."""


def validate_subject_pack_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("schema_version"), str) or not config["schema_version"].strip():
        raise SubjectPackValidationError("Subject pack config requires schema_version.")

    for key in TAXONOMY_LIST_KEYS:
        values = config.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise SubjectPackValidationError(f"Subject pack config {key!r} must be a list of non-empty strings.")

    templates = config.get("rubric_templates", [])
    if not isinstance(templates, list):
        raise SubjectPackValidationError("Subject pack rubric_templates must be a list when provided.")
    for template in templates:
        if not isinstance(template, dict) or not isinstance(template.get("key"), str) or not template["key"].strip():
            raise SubjectPackValidationError("Every rubric template reference requires a non-empty key.")


def create_subject_pack(
    db: Session,
    *,
    organization_id: uuid.UUID | None,
    key: str,
    name: str,
    config: dict[str, Any],
    description: str | None = None,
) -> SubjectPack:
    validate_subject_pack_config(config)
    existing_pack = db.scalar(
        select(SubjectPack).where(
            SubjectPack.organization_id == organization_id,
            SubjectPack.key == key,
        )
    )
    if existing_pack is not None:
        scope = "global" if organization_id is None else str(organization_id)
        raise SubjectPackValidationError(f"Subject pack {key!r} already exists for organization scope {scope}.")

    pack = SubjectPack(
        organization_id=organization_id,
        key=key,
        name=name,
        description=description,
        schema_version=config["schema_version"],
        config=copy.deepcopy(config),
        status="active",
    )
    db.add(pack)
    db.flush()
    return pack


def resolve_active_subject_pack(
    db: Session,
    *,
    key: str,
    organization_id: uuid.UUID | None,
    allow_global: bool = True,
) -> SubjectPack | None:
    if organization_id is not None:
        pack = db.scalar(
            select(SubjectPack).where(
                SubjectPack.organization_id == organization_id,
                SubjectPack.key == key,
                SubjectPack.status == "active",
            )
        )
        if pack is not None:
            return pack

    if not allow_global:
        return None

    return db.scalar(
        select(SubjectPack).where(
            SubjectPack.organization_id.is_(None),
            SubjectPack.key == key,
            SubjectPack.status == "active",
        )
    )


def subject_pack_summary(pack: SubjectPack) -> dict[str, Any]:
    return {
        "id": str(pack.id) if pack.id is not None else None,
        "organization_id": str(pack.organization_id) if pack.organization_id is not None else None,
        "key": pack.key,
        "name": pack.name,
        "schema_version": pack.schema_version,
        "status": pack.status,
        "assessment_types": list(pack.config.get("assessment_types", [])),
        "evidence_types": list(pack.config.get("evidence_types", [])),
        "output_types": list(pack.config.get("output_types", [])),
        "rubric_types": list(pack.config.get("rubric_types", [])),
    }
