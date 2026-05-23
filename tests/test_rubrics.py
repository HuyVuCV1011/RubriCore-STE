import uuid
from decimal import Decimal

import pytest

from app.db.models import (
    AuditEvent,
    PerformanceLevel,
    Rubric,
    RubricBinding,
    RubricCriterion,
    RubricDescriptor,
    RubricVersion,
)
from app.db.services.rubrics import (
    PublishedRubricVersionImmutableError,
    RubricValidationError,
    bind_rubric_version,
    calculate_deterministic_score,
    create_rubric,
    ordered_criteria,
    ordered_performance_levels,
    publish_rubric_version,
    update_published_rubric_version,
    validate_rubric_schema,
)


class RecordingSession:
    def __init__(self, get_result: object | None = None) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.get_result = get_result

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        self.flush_count += 1
        for record in self.added:
            if hasattr(record, "id") and record.id is None:
                record.id = uuid.uuid4()

    def get(self, _: object, __: object) -> object | None:
        return self.get_result


def rubric_schema() -> dict:
    return {
        "schema_version": "1.0",
        "criteria": [
            {"key": "clarity", "label": "Clarity", "position": 1, "weight": "1"},
            {"key": "correctness", "label": "Correctness", "position": 0, "weight": "2"},
        ],
        "performance_levels": [
            {"key": "meets", "label": "Meets", "position": 2, "score": "2"},
            {"key": "needs_revision", "label": "Needs Revision", "position": 0, "score": "0"},
            {"key": "partial", "label": "Partial", "position": 1, "score": "1"},
        ],
        "descriptors": [
            {
                "criterion_key": "correctness",
                "performance_level_key": "needs_revision",
                "narrative": "Does not compute the requested result.",
            },
            {
                "criterion_key": "correctness",
                "performance_level_key": "partial",
                "narrative": "Computes the main path but misses edge cases.",
            },
            {
                "criterion_key": "correctness",
                "performance_level_key": "meets",
                "narrative": "Computes the requested result accurately.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "needs_revision",
                "narrative": "The solution is difficult to inspect.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "partial",
                "narrative": "The solution is readable in parts.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "meets",
                "narrative": "The solution is clear and direct.",
            },
        ],
    }


def test_rubric_framework_models_are_registered() -> None:
    assert RubricCriterion.__tablename__ == "rubric_criteria"
    assert PerformanceLevel.__tablename__ == "performance_levels"
    assert RubricDescriptor.__tablename__ == "rubric_descriptors"
    assert RubricBinding.__tablename__ == "rubric_bindings"

    assert "slug" in Rubric.__table__.columns
    assert "metadata_payload" in Rubric.__table__.columns
    assert "source_metadata" in RubricVersion.__table__.columns
    assert RubricBinding.__table__.columns["rubric_version_id"].nullable is False


def test_rubric_creation_validates_and_records_a_draft() -> None:
    session = RecordingSession()
    organization_id = uuid.uuid4()
    rubric_type_id = uuid.uuid4()

    rubric = create_rubric(
        session,  # type: ignore[arg-type]
        organization_id=organization_id,
        rubric_type_id=rubric_type_id,
        title="Python Score Summary",
        draft_schema=rubric_schema(),
        metadata_payload={"subject_agnostic": True},
    )

    assert rubric.organization_id == organization_id
    assert rubric.rubric_type_id == rubric_type_id
    assert rubric.slug == "python-score-summary"
    assert rubric.status == "draft"
    assert rubric.metadata_payload == {"subject_agnostic": True}
    audit_events = [record for record in session.added if isinstance(record, AuditEvent)]
    assert [record for record in session.added if isinstance(record, Rubric)] == [rubric]
    assert audit_events[0].action == "rubric.created"
    assert audit_events[0].entity_type == "rubric"
    assert audit_events[0].entity_id == rubric.id
    assert audit_events[0].new_state["status"] == "draft"
    assert session.flush_count == 1


def test_publish_rubric_version_records_audit_event() -> None:
    rubric = Rubric(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        rubric_type_id=uuid.uuid4(),
        title="Python Score Summary",
        slug="python-score-summary",
        status="draft",
        draft_schema=rubric_schema(),
    )
    publisher_id = uuid.uuid4()
    session = RecordingSession()

    version = publish_rubric_version(
        session,  # type: ignore[arg-type]
        rubric=rubric,
        published_by_user_id=publisher_id,
        source_metadata={"source": "unit_test"},
        request_id="req-publish-rubric",
    )

    audit_events = [record for record in session.added if isinstance(record, AuditEvent)]
    assert version.version_number == 1
    assert rubric.latest_version_number == 1
    assert audit_events[0].action == "rubric_version.published"
    assert audit_events[0].entity_type == "rubric_version"
    assert audit_events[0].entity_id == version.id
    assert audit_events[0].actor_user_id == publisher_id
    assert audit_events[0].request_id == "req-publish-rubric"
    assert audit_events[0].new_state["criteria"] == ["correctness", "clarity"]


def test_published_rubric_versions_are_not_silently_mutable() -> None:
    with pytest.raises(PublishedRubricVersionImmutableError):
        update_published_rubric_version()


def test_criterion_ordering_is_position_based() -> None:
    assert [criterion["key"] for criterion in ordered_criteria(rubric_schema())] == ["correctness", "clarity"]


def test_performance_level_ordering_is_position_based() -> None:
    assert [level["key"] for level in ordered_performance_levels(rubric_schema())] == [
        "needs_revision",
        "partial",
        "meets",
    ]


def test_descriptor_completeness_is_required() -> None:
    schema = rubric_schema()
    schema["descriptors"] = schema["descriptors"][:-1]

    with pytest.raises(RubricValidationError, match="Missing descriptors"):
        validate_rubric_schema(schema)


def test_bind_rubric_version_to_evaluation_context_records_audit_event() -> None:
    version = RubricVersion(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        rubric_id=uuid.uuid4(),
        version_number=1,
        title="Published Rubric",
        rubric_schema=rubric_schema(),
        source_metadata={"source": "unit_test"},
        status="published",
    )
    session = RecordingSession(get_result=version)

    binding = bind_rubric_version(
        session,  # type: ignore[arg-type]
        organization_id=version.organization_id,
        rubric_version_id=version.id,
        context_type="evaluation_context",
        external_context_key="fixture:python-score-summary",
        source="fixture_import",
        metadata_payload={"reason": "synthetic fixture"},
        reason="synthetic fixture",
        request_id="req-bind-rubric",
    )

    assert binding.rubric_version_id == version.id
    assert binding.context_type == "evaluation_context"
    assert binding.external_context_key == "fixture:python-score-summary"
    assert binding.source == "fixture_import"
    assert binding.metadata_payload == {"reason": "synthetic fixture"}
    audit_events = [record for record in session.added if isinstance(record, AuditEvent)]
    assert [record for record in session.added if isinstance(record, RubricBinding)] == [binding]
    assert audit_events[0].action == "rubric_binding.created"
    assert audit_events[0].entity_type == "rubric_binding"
    assert audit_events[0].entity_id == binding.id
    assert audit_events[0].actor_source == "fixture_import"
    assert audit_events[0].reason == "synthetic fixture"
    assert audit_events[0].request_id == "req-bind-rubric"
    assert audit_events[0].new_state["external_context_key"] == "fixture:python-score-summary"
    assert session.flush_count == 1


def test_binding_requires_published_version() -> None:
    version = RubricVersion(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        rubric_id=uuid.uuid4(),
        version_number=1,
        title="Archived Rubric",
        rubric_schema=rubric_schema(),
        status="archived",
    )

    with pytest.raises(RubricValidationError, match="published rubric version"):
        bind_rubric_version(
            RecordingSession(get_result=version),  # type: ignore[arg-type]
            organization_id=version.organization_id,
            rubric_version_id=version.id,
            context_type="evaluation_context",
            external_context_key="fixture:archived",
        )


def test_deterministic_score_summary_uses_levels_and_weights() -> None:
    summary = calculate_deterministic_score(
        rubric_schema(),
        {
            "correctness": "meets",
            "clarity": "partial",
        },
    )

    assert summary.criterion_scores == {
        "correctness": Decimal("4"),
        "clarity": Decimal("1"),
    }
    assert summary.total_score == Decimal("5")
    assert summary.max_score == Decimal("6")
