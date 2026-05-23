import uuid
from typing import Any

import pytest

from app.db.models import AuditEvent, Rubric, RubricSuggestion
from app.db.services.rubric_suggestions import (
    RubricSuggestionError,
    accept_rubric_suggestion,
    create_rubric_suggestion,
    reject_rubric_suggestion,
)


class RecordingSession:
    def __init__(self, *, get_results: dict[tuple[object, object], object] | None = None) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.get_results = get_results or {}

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        self.flush_count += 1
        for record in self.added:
            if hasattr(record, "id") and record.id is None:
                record.id = uuid.uuid4()

    def get(self, entity: object, ident: object) -> object | None:
        return self.get_results.get((entity, ident))


def rubric_schema() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "criteria": [
            {"key": "correctness", "label": "Correctness", "position": 0, "weight": "2"},
        ],
        "performance_levels": [
            {"key": "needs_revision", "label": "Needs Revision", "position": 0, "score": "0"},
            {"key": "meets", "label": "Meets", "position": 1, "score": "2"},
        ],
        "descriptors": [
            {
                "criterion_key": "correctness",
                "performance_level_key": "needs_revision",
                "narrative": "Does not compute the requested summary.",
            },
            {
                "criterion_key": "correctness",
                "performance_level_key": "meets",
                "narrative": "Computes the requested summary.",
            },
        ],
    }


def records(session: RecordingSession, record_type: type) -> list:
    return [record for record in session.added if isinstance(record, record_type)]


def citation() -> dict[str, Any]:
    return {
        "knowledge_source_id": str(uuid.uuid4()),
        "chunk_id": str(uuid.uuid4()),
        "chunk_key": "chunk-0000",
        "heading_path": ["Teacher Notes"],
        "content_hash": "abc123",
    }


def criterion_payload() -> dict[str, Any]:
    return {
        "criterion": {
            "key": "edge_cases",
            "label": "Edge Cases",
            "description": "Handles empty lists and threshold equality.",
            "weight": "1",
        },
        "descriptors": [
            {
                "performance_level_key": "needs_revision",
                "narrative": "Misses empty lists or threshold equality.",
            },
            {
                "performance_level_key": "meets",
                "narrative": "Handles empty lists and threshold equality.",
            },
        ],
    }


def test_create_rubric_suggestion_requires_citations_and_does_not_mutate_rubric() -> None:
    session = RecordingSession()
    organization_id = uuid.uuid4()
    rubric_id = uuid.uuid4()

    with pytest.raises(RubricSuggestionError, match="citation"):
        create_rubric_suggestion(
            session,  # type: ignore[arg-type]
            organization_id=organization_id,
            target_rubric_id=rubric_id,
            suggestion_type="criterion",
            suggestion_payload=criterion_payload(),
            source_citations=[],
        )

    suggestion = create_rubric_suggestion(
        session,  # type: ignore[arg-type]
        organization_id=organization_id,
        target_rubric_id=rubric_id,
        suggestion_type="criterion",
        suggestion_payload=criterion_payload(),
        source_citations=[citation()],
    )

    assert suggestion.status == "draft"
    assert suggestion.target_rubric_id == rubric_id
    assert records(session, RubricSuggestion) == [suggestion]
    assert records(session, AuditEvent)[0].action == "rubric_suggestion.created"


def test_reject_rubric_suggestion_records_teacher_decision_and_audit() -> None:
    reviewer_id = uuid.uuid4()
    suggestion = RubricSuggestion(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        target_rubric_id=uuid.uuid4(),
        suggestion_type="criterion",
        status="draft",
        suggestion_payload=criterion_payload(),
        source_citations=[citation()],
        metadata_payload={},
    )
    session = RecordingSession()

    reject_rubric_suggestion(
        session,  # type: ignore[arg-type]
        suggestion=suggestion,
        reviewed_by_user_id=reviewer_id,
        reason="Already covered by existing criterion.",
    )

    assert suggestion.status == "rejected"
    assert suggestion.reviewed_by_user_id == reviewer_id
    assert records(session, AuditEvent)[0].action == "rubric_suggestion.rejected"


def test_accept_rubric_suggestion_updates_only_draft_schema() -> None:
    reviewer_id = uuid.uuid4()
    rubric = Rubric(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        rubric_type_id=uuid.uuid4(),
        title="Python Rubric",
        status="published",
        draft_schema=rubric_schema(),
        latest_version_number=1,
        metadata_payload={},
    )
    original_schema = rubric.draft_schema.copy()
    suggestion = RubricSuggestion(
        id=uuid.uuid4(),
        organization_id=rubric.organization_id,
        target_rubric_id=rubric.id,
        suggestion_type="criterion",
        status="draft",
        suggestion_payload=criterion_payload(),
        source_citations=[citation()],
        metadata_payload={},
    )
    session = RecordingSession(get_results={(Rubric, rubric.id): rubric})

    accept_rubric_suggestion(
        session,  # type: ignore[arg-type]
        suggestion=suggestion,
        reviewed_by_user_id=reviewer_id,
        reason="Teacher wants explicit edge-case criterion.",
    )

    assert suggestion.status == "accepted"
    assert suggestion.reviewed_by_user_id == reviewer_id
    assert rubric.status == "draft"
    assert rubric.latest_version_number == 1
    assert original_schema["criteria"][0]["key"] == "correctness"
    assert [criterion["key"] for criterion in rubric.draft_schema["criteria"]] == ["correctness", "edge_cases"]
    assert "knowledge_suggestion_id" in rubric.draft_schema["criteria"][1]["metadata_payload"]
    assert [event.action for event in records(session, AuditEvent)] == [
        "rubric_suggestion.accepted",
        "rubric.draft_updated_from_suggestion",
    ]


def test_accept_rubric_suggestion_rejects_duplicate_criterion_key() -> None:
    rubric = Rubric(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        rubric_type_id=uuid.uuid4(),
        title="Python Rubric",
        status="draft",
        draft_schema=rubric_schema(),
        metadata_payload={},
    )
    suggestion = RubricSuggestion(
        id=uuid.uuid4(),
        organization_id=rubric.organization_id,
        target_rubric_id=rubric.id,
        suggestion_type="criterion",
        status="draft",
        suggestion_payload={
            "criterion": {"key": "correctness", "label": "Correctness", "position": 1},
            "descriptors": [],
        },
        source_citations=[citation()],
        metadata_payload={},
    )
    session = RecordingSession(get_results={(Rubric, rubric.id): rubric})

    with pytest.raises(RubricSuggestionError, match="already exists"):
        accept_rubric_suggestion(
            session,  # type: ignore[arg-type]
            suggestion=suggestion,
            reviewed_by_user_id=uuid.uuid4(),
            reason="Duplicate should fail.",
        )
