from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    PerformanceLevel,
    Rubric,
    RubricBinding,
    RubricCriterion,
    RubricDescriptor,
    RubricVersion,
)


RUBRIC_SCHEMA_VERSION = "1.0"


class RubricValidationError(ValueError):
    """Raised when a rubric definition is incomplete or structurally invalid."""


class PublishedRubricVersionImmutableError(ValueError):
    """Raised when code attempts to silently mutate a published rubric version."""


@dataclass(frozen=True)
class RubricScoreSummary:
    total_score: Decimal
    max_score: Decimal
    criterion_scores: dict[str, Decimal]


def slugify_rubric_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "rubric"


def ordered_criteria(rubric_schema: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(rubric_schema.get("criteria", []), key=lambda item: item["position"])


def ordered_performance_levels(rubric_schema: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(rubric_schema.get("performance_levels", []), key=lambda item: item["position"])


def validate_rubric_schema(rubric_schema: dict[str, Any]) -> None:
    criteria = rubric_schema.get("criteria")
    levels = rubric_schema.get("performance_levels")
    descriptors = rubric_schema.get("descriptors")

    if not isinstance(criteria, list) or not criteria:
        raise RubricValidationError("Rubric schema must include at least one criterion.")
    if not isinstance(levels, list) or not levels:
        raise RubricValidationError("Rubric schema must include at least one performance level.")
    if not isinstance(descriptors, list):
        raise RubricValidationError("Rubric schema must include descriptors.")

    criterion_keys = _validate_keyed_items(criteria, "criteria")
    level_keys = _validate_keyed_items(levels, "performance_levels")
    _validate_positions(criteria, "criteria")
    _validate_positions(levels, "performance_levels")

    for criterion in criteria:
        weight = criterion.get("weight")
        if weight is not None and Decimal(str(weight)) <= 0:
            raise RubricValidationError(f"Criterion {criterion['key']} weight must be positive when provided.")

    for level in levels:
        if "score" not in level:
            raise RubricValidationError(f"Performance level {level['key']} must include a score.")
        if Decimal(str(level["score"])) < 0:
            raise RubricValidationError(f"Performance level {level['key']} score cannot be negative.")

    descriptor_pairs: set[tuple[str, str]] = set()
    for descriptor in descriptors:
        criterion_key = descriptor.get("criterion_key")
        level_key = descriptor.get("performance_level_key")
        narrative = descriptor.get("narrative")
        if criterion_key not in criterion_keys:
            raise RubricValidationError(f"Descriptor references unknown criterion {criterion_key!r}.")
        if level_key not in level_keys:
            raise RubricValidationError(f"Descriptor references unknown performance level {level_key!r}.")
        if not isinstance(narrative, str) or not narrative.strip():
            raise RubricValidationError(
                f"Descriptor for criterion {criterion_key!r} and level {level_key!r} must include narrative text."
            )
        pair = (criterion_key, level_key)
        if pair in descriptor_pairs:
            raise RubricValidationError(
                f"Duplicate descriptor for criterion {criterion_key!r} and level {level_key!r}."
            )
        descriptor_pairs.add(pair)

    missing_pairs = {
        (criterion_key, level_key)
        for criterion_key in criterion_keys
        for level_key in level_keys
        if (criterion_key, level_key) not in descriptor_pairs
    }
    if missing_pairs:
        formatted = ", ".join(f"{criterion_key}/{level_key}" for criterion_key, level_key in sorted(missing_pairs))
        raise RubricValidationError(f"Missing descriptors for: {formatted}.")


def create_rubric(
    db: Session,
    *,
    organization_id: UUID,
    rubric_type_id: UUID,
    title: str,
    draft_schema: dict[str, Any],
    created_by_user_id: UUID | None = None,
    slug: str | None = None,
    description: str | None = None,
    metadata_payload: dict[str, Any] | None = None,
    actor_source: str = "teacher",
    reason: str | None = None,
    request_id: str | None = None,
) -> Rubric:
    validate_rubric_schema(draft_schema)
    rubric = Rubric(
        organization_id=organization_id,
        rubric_type_id=rubric_type_id,
        created_by_user_id=created_by_user_id,
        title=title,
        slug=slug or slugify_rubric_title(title),
        description=description,
        status="draft",
        draft_schema=copy.deepcopy(draft_schema),
        metadata_payload=metadata_payload or {},
    )
    db.add(rubric)
    db.flush()
    _audit_rubric_event(
        db,
        organization_id=organization_id,
        actor_user_id=created_by_user_id,
        actor_source=actor_source,
        action="rubric.created",
        entity_type="rubric",
        entity_id=rubric.id,
        previous_state={},
        new_state={
            "id": str(rubric.id) if rubric.id is not None else None,
            "title": rubric.title,
            "slug": rubric.slug,
            "status": rubric.status,
            "rubric_type_id": str(rubric_type_id),
        },
        reason=reason,
        request_id=request_id,
    )
    return rubric


def publish_rubric_version(
    db: Session,
    *,
    rubric: Rubric,
    published_by_user_id: UUID | None = None,
    source_metadata: dict[str, Any] | None = None,
    actor_source: str = "teacher",
    reason: str | None = None,
    request_id: str | None = None,
) -> RubricVersion:
    validate_rubric_schema(rubric.draft_schema)
    next_version = (rubric.latest_version_number or 0) + 1
    rubric_schema = copy.deepcopy(rubric.draft_schema)

    version = RubricVersion(
        organization_id=rubric.organization_id,
        rubric_id=rubric.id,
        version_number=next_version,
        title=rubric.title,
        schema_version=RUBRIC_SCHEMA_VERSION,
        rubric_schema=rubric_schema,
        source_metadata=source_metadata or {},
        published_by_user_id=published_by_user_id,
        status="published",
    )
    db.add(version)
    db.flush()
    _materialize_version_structure(db, version, rubric_schema)
    rubric.latest_version_number = next_version
    rubric.status = "published"
    db.flush()
    _audit_rubric_event(
        db,
        organization_id=rubric.organization_id,
        actor_user_id=published_by_user_id,
        actor_source=actor_source,
        action="rubric_version.published",
        entity_type="rubric_version",
        entity_id=version.id,
        previous_state={
            "rubric_id": str(rubric.id) if rubric.id is not None else None,
            "latest_version_number": next_version - 1 if next_version > 1 else None,
            "status": "draft" if next_version == 1 else "published",
        },
        new_state={
            "rubric_id": str(rubric.id) if rubric.id is not None else None,
            "rubric_version_id": str(version.id) if version.id is not None else None,
            "version_number": version.version_number,
            "status": version.status,
            "schema_version": version.schema_version,
            "criteria": [criterion["key"] for criterion in ordered_criteria(rubric_schema)],
            "performance_levels": [level["key"] for level in ordered_performance_levels(rubric_schema)],
            "source_metadata": copy.deepcopy(version.source_metadata),
        },
        reason=reason,
        request_id=request_id,
    )
    return version


def update_published_rubric_version(*_: Any, **__: Any) -> None:
    raise PublishedRubricVersionImmutableError("Published rubric versions are immutable; create a new version instead.")


def bind_rubric_version(
    db: Session,
    *,
    organization_id: UUID,
    rubric_version_id: UUID,
    context_type: str,
    assessment_id: UUID | None = None,
    assessment_item_id: UUID | None = None,
    external_context_key: str | None = None,
    bound_by_user_id: UUID | None = None,
    source: str = "teacher",
    metadata_payload: dict[str, Any] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> RubricBinding:
    if context_type == "assessment" and assessment_id is None:
        raise RubricValidationError("Assessment bindings require assessment_id.")
    if context_type == "assessment_item" and assessment_item_id is None:
        raise RubricValidationError("Assessment item bindings require assessment_item_id.")
    if context_type == "evaluation_context" and not external_context_key:
        raise RubricValidationError("Evaluation context bindings require external_context_key.")

    version = db.get(RubricVersion, rubric_version_id)
    if version is None or version.status != "published":
        raise RubricValidationError("Rubric bindings require an existing published rubric version.")

    binding = RubricBinding(
        organization_id=organization_id,
        rubric_version_id=rubric_version_id,
        assessment_id=assessment_id,
        assessment_item_id=assessment_item_id,
        external_context_key=external_context_key,
        context_type=context_type,
        status="active",
        bound_by_user_id=bound_by_user_id,
        source=source,
        metadata_payload=metadata_payload or {},
    )
    db.add(binding)
    db.flush()
    _audit_rubric_event(
        db,
        organization_id=organization_id,
        assessment_id=assessment_id,
        actor_user_id=bound_by_user_id,
        actor_source=source,
        action="rubric_binding.created",
        entity_type="rubric_binding",
        entity_id=binding.id,
        previous_state={},
        new_state={
            "rubric_binding_id": str(binding.id) if binding.id is not None else None,
            "rubric_version_id": str(rubric_version_id),
            "context_type": context_type,
            "assessment_id": str(assessment_id) if assessment_id is not None else None,
            "assessment_item_id": str(assessment_item_id) if assessment_item_id is not None else None,
            "external_context_key": external_context_key,
            "status": binding.status,
            "source": source,
        },
        reason=reason,
        request_id=request_id,
    )
    return binding


def _audit_rubric_event(
    db: Session,
    *,
    organization_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    actor_user_id: UUID | None,
    actor_source: str,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    assessment_id: UUID | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        assessment_id=assessment_id,
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


def calculate_deterministic_score(
    rubric_schema: dict[str, Any],
    selected_levels_by_criterion: dict[str, str],
) -> RubricScoreSummary:
    validate_rubric_schema(rubric_schema)
    levels = {level["key"]: Decimal(str(level["score"])) for level in rubric_schema["performance_levels"]}
    criteria = {criterion["key"]: Decimal(str(criterion.get("weight", 1))) for criterion in rubric_schema["criteria"]}
    max_level_score = max(levels.values())
    criterion_scores: dict[str, Decimal] = {}

    unknown_criteria = set(selected_levels_by_criterion) - set(criteria)
    if unknown_criteria:
        formatted = ", ".join(sorted(unknown_criteria))
        raise RubricValidationError(f"Scores include unknown criteria: {formatted}.")

    for criterion_key, level_key in selected_levels_by_criterion.items():
        if level_key not in levels:
            raise RubricValidationError(f"Criterion {criterion_key!r} selected unknown level {level_key!r}.")
        criterion_scores[criterion_key] = levels[level_key] * criteria[criterion_key]

    max_score = sum((max_level_score * weight for weight in criteria.values()), Decimal("0"))
    total_score = sum(criterion_scores.values(), Decimal("0"))
    return RubricScoreSummary(total_score=total_score, max_score=max_score, criterion_scores=criterion_scores)


def _validate_keyed_items(items: list[dict[str, Any]], label: str) -> set[str]:
    keys: set[str] = set()
    for item in items:
        key = item.get("key")
        item_label = item.get("label")
        if not isinstance(key, str) or not key.strip():
            raise RubricValidationError(f"Every {label} item must include a non-empty key.")
        if not isinstance(item_label, str) or not item_label.strip():
            raise RubricValidationError(f"{label} item {key!r} must include a non-empty label.")
        if key in keys:
            raise RubricValidationError(f"Duplicate {label} key {key!r}.")
        keys.add(key)
    return keys


def _validate_positions(items: list[dict[str, Any]], label: str) -> None:
    positions: set[int] = set()
    for item in items:
        position = item.get("position")
        if not isinstance(position, int) or position < 0:
            raise RubricValidationError(
                f"{label} item {item.get('key')!r} must include a non-negative integer position."
            )
        if position in positions:
            raise RubricValidationError(f"Duplicate {label} position {position}.")
        positions.add(position)


def _materialize_version_structure(db: Session, version: RubricVersion, rubric_schema: dict[str, Any]) -> None:
    criteria_by_key: dict[str, RubricCriterion] = {}
    levels_by_key: dict[str, PerformanceLevel] = {}

    for criterion in ordered_criteria(rubric_schema):
        record = RubricCriterion(
            organization_id=version.organization_id,
            rubric_version_id=version.id,
            key=criterion["key"],
            label=criterion["label"],
            description=criterion.get("description"),
            weight=Decimal(str(criterion["weight"])) if criterion.get("weight") is not None else None,
            position=criterion["position"],
            evaluation_hints=criterion.get("evaluation_hints", {}),
        )
        db.add(record)
        criteria_by_key[record.key] = record

    for level in ordered_performance_levels(rubric_schema):
        record = PerformanceLevel(
            organization_id=version.organization_id,
            rubric_version_id=version.id,
            key=level["key"],
            label=level["label"],
            description=level.get("description"),
            score=Decimal(str(level["score"])),
            position=level["position"],
            metadata_payload=level.get("metadata_payload", {}),
        )
        db.add(record)
        levels_by_key[record.key] = record

    db.flush()

    for descriptor in rubric_schema["descriptors"]:
        criterion_key = descriptor["criterion_key"]
        level_key = descriptor["performance_level_key"]
        db.add(
            RubricDescriptor(
                organization_id=version.organization_id,
                rubric_version_id=version.id,
                criterion_id=criteria_by_key[criterion_key].id,
                performance_level_id=levels_by_key[level_key].id,
                criterion_key=criterion_key,
                performance_level_key=level_key,
                narrative=descriptor["narrative"],
                evaluation_hints=descriptor.get("evaluation_hints", {}),
                metadata_payload=descriptor.get("metadata_payload", {}),
            )
        )


def get_active_rubric_binding_for_assessment_item(
    db: Session,
    *,
    assessment_item_id: UUID,
) -> RubricBinding | None:
    return db.scalar(
        select(RubricBinding)
        .where(
            RubricBinding.assessment_item_id == assessment_item_id,
            RubricBinding.status == "active",
        )
        .order_by(RubricBinding.created_at.desc())
    )
