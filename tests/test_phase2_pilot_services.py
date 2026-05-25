import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AnswerKey,
    AnswerKeyVersion,
    Assessment,
    AssessmentType,
    AuditEvent,
    GradingResult,
    GradingRun,
    Learner,
    Organization,
    ReviewTask,
    Rubric,
    SubjectPack,
    Submission,
    TeacherReview,
)
from app.db.services.answer_keys import (
    AnswerKeyValidationError,
    create_answer_key,
    publish_answer_key_version,
    validate_answer_key_payload,
)
from app.db.services.calibration import reviewed_example_payload
from app.db.services.pilot_io import export_grading_result, validate_fixture_manifest
from app.db.services.review_queue import list_review_tasks, review_task_summary
from app.db.services.rubric_authoring import RubricAuthoringError, update_rubric_draft
from app.db.services.subject_packs import (
    SubjectPackValidationError,
    create_subject_pack,
    resolve_active_subject_pack,
    subject_pack_summary,
    validate_subject_pack_config,
)


class RecordingSession:
    def __init__(
        self,
        *,
        scalar_results: list[object | None] | None = None,
        scalars_results: list[object] | None = None,
    ) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.scalar_results = list(scalar_results or [])
        self.scalars_results = list(scalars_results or [])

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        self.flush_count += 1
        for record in self.added:
            if hasattr(record, "id") and record.id is None:
                record.id = uuid.uuid4()

    def scalar(self, _: object) -> object | None:
        return self.scalar_results.pop(0) if self.scalar_results else None

    def scalars(self, _: object) -> list[object]:
        return self.scalars_results


def records(session: RecordingSession, record_type: type) -> list:
    return [record for record in session.added if isinstance(record, record_type)]


def rubric_schema() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "criteria": [
            {"key": "correctness", "label": "Correctness", "position": 0, "weight": "1"},
        ],
        "performance_levels": [
            {"key": "needs_revision", "label": "Needs Revision", "position": 0, "score": "0"},
            {"key": "meets", "label": "Meets", "position": 1, "score": "2"},
        ],
        "descriptors": [
            {
                "criterion_key": "correctness",
                "performance_level_key": "needs_revision",
                "narrative": "Does not meet the requirement.",
            },
            {
                "criterion_key": "correctness",
                "performance_level_key": "meets",
                "narrative": "Meets the requirement.",
            },
        ],
    }


@pytest.fixture
def db_session() -> Iterator[Session]:
    try:
        database_url = get_settings().database_url
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            required_tables = {
                "organizations",
                "learners",
                "submissions",
                "review_tasks",
                "subject_packs",
            }
            existing_tables = set(inspect(connection).get_table_names())
            if not required_tables.issubset(existing_tables):
                missing = ", ".join(sorted(required_tables - existing_tables))
                pytest.skip(f"Database is not migrated for Phase 2 pilot-service tests; missing: {missing}")
            if connection.in_transaction():
                connection.rollback()

            transaction = connection.begin()
            session = Session(bind=connection)
            try:
                yield session
            finally:
                session.close()
                transaction.rollback()
    except OperationalError as exc:
        pytest.skip(f"Database-backed pilot-service tests require a reachable dev database: {exc}")


def subject_pack_config() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "assessment_types": ["code-assignment"],
        "evidence_types": ["code"],
        "output_types": ["executable-behavior"],
        "rubric_types": ["analytic-rubric"],
        "rubric_templates": [{"key": "python-score-summary"}],
    }


def test_subject_pack_validation_and_summary() -> None:
    config = subject_pack_config()
    validate_subject_pack_config(config)
    session = RecordingSession()

    pack = create_subject_pack(
        session,  # type: ignore[arg-type]
        organization_id=uuid.uuid4(),
        key="python-pilot",
        name="Python Pilot",
        config=config,
    )

    assert pack.status == "active"
    assert subject_pack_summary(pack)["assessment_types"] == ["code-assignment"]

    with pytest.raises(SubjectPackValidationError):
        validate_subject_pack_config({"schema_version": "1.0", "assessment_types": [None]})


def test_subject_pack_create_rejects_duplicate_scope() -> None:
    existing = SubjectPack(
        id=uuid.uuid4(),
        organization_id=None,
        key="python-pilot",
        name="Existing Python Pilot",
        schema_version="1.0",
        config=subject_pack_config(),
        status="active",
    )
    session = RecordingSession(scalar_results=[existing])

    with pytest.raises(SubjectPackValidationError, match="already exists"):
        create_subject_pack(
            session,  # type: ignore[arg-type]
            organization_id=None,
            key="python-pilot",
            name="Python Pilot",
            config=subject_pack_config(),
        )

    assert records(session, SubjectPack) == []


def test_rubric_authoring_updates_draft_and_records_audit() -> None:
    schema = rubric_schema()
    updated_schema = rubric_schema()
    updated_schema["criteria"][0]["label"] = "Updated Correctness"
    rubric = Rubric(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        rubric_type_id=uuid.uuid4(),
        title="Draft Rubric",
        status="published",
        draft_schema=schema,
        latest_version_number=1,
        metadata_payload={},
    )
    session = RecordingSession()

    update_rubric_draft(
        session,  # type: ignore[arg-type]
        rubric=rubric,
        draft_schema=updated_schema,
        title="Updated Rubric",
        reason="Teacher edit.",
    )

    assert rubric.status == "draft"
    assert rubric.title == "Updated Rubric"
    assert records(session, AuditEvent)[0].action == "rubric.draft_updated"

    rubric.status = "archived"
    with pytest.raises(RubricAuthoringError):
        update_rubric_draft(session, rubric=rubric, draft_schema=updated_schema)  # type: ignore[arg-type]


def test_answer_key_create_publish_and_validation() -> None:
    payload = {"accepted": ["42"], "metadata": {"source": "unit_test"}}
    validate_answer_key_payload(payload)
    session = RecordingSession()

    answer_key = create_answer_key(
        session,  # type: ignore[arg-type]
        organization_id=uuid.uuid4(),
        assessment_item_id=uuid.uuid4(),
        title="Answer Key",
        draft_key=payload,
    )
    version = publish_answer_key_version(
        session,  # type: ignore[arg-type]
        answer_key=answer_key,
        reason="Ready for pilot.",
    )

    assert answer_key.status == "published"
    assert answer_key.latest_version_number == 1
    assert version.version_number == 1
    assert records(session, AnswerKey) == [answer_key]
    assert records(session, AnswerKeyVersion) == [version]
    assert records(session, AuditEvent)[0].action == "answer_key_version.published"

    with pytest.raises(AnswerKeyValidationError):
        validate_answer_key_payload({"accepted": []})


def test_review_queue_orders_and_summarizes_tasks() -> None:
    organization_id = uuid.uuid4()
    low = ReviewTask(
        id=uuid.uuid4(),
        organization_id=organization_id,
        submission_id=uuid.uuid4(),
        status="open",
        priority="low",
        escalation_reason="low_confidence",
        policy_payload={},
    )
    urgent = ReviewTask(
        id=uuid.uuid4(),
        organization_id=organization_id,
        submission_id=uuid.uuid4(),
        status="open",
        priority="urgent",
        escalation_reason="policy_exception",
        policy_payload={"reason": "pilot"},
    )
    low.created_at = datetime(2026, 1, 2, tzinfo=UTC)
    urgent.created_at = datetime(2026, 1, 3, tzinfo=UTC)
    session = RecordingSession(scalars_results=[low, urgent])

    tasks = list_review_tasks(
        session,  # type: ignore[arg-type]
        organization_id=organization_id,
        statuses={"open"},
    )

    assert tasks == [urgent, low]
    assert review_task_summary(urgent)["priority"] == "urgent"
    assert review_task_summary(urgent)["policy_payload"] == {"reason": "pilot"}


def test_manifest_validation_and_result_export() -> None:
    manifest = {
        "fixture_set": "demo",
        "title": "Demo",
        "privacy": "public_safe",
        "files": [
            {
                "path": "assessment_materials/problem.md",
                "purpose": "assessment_material",
                "description": "Prompt.",
            }
        ],
    }
    assert validate_fixture_manifest(manifest) == []
    assert validate_fixture_manifest({**manifest, "privacy": "private"})

    result = GradingResult(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        grading_run_id=uuid.uuid4(),
        result_type="final",
        status="finalized",
        total_score=Decimal("4"),
        max_score=Decimal("5"),
        confidence=Decimal("0.9000"),
        feedback="Good work.",
        explanation_payload={"source": "unit_test"},
    )
    exported = export_grading_result(result)

    assert exported["total_score"] == "4"
    assert exported["confidence"] == "0.9000"
    assert exported["explanation_payload"] == {"source": "unit_test"}


def test_reviewed_example_payload_requires_finalized_result() -> None:
    run = GradingRun(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        submission_id=uuid.uuid4(),
        status="completed",
        context_payload={},
    )
    result = GradingResult(
        id=uuid.uuid4(),
        organization_id=run.organization_id,
        grading_run_id=run.id,
        rubric_version_id=uuid.uuid4(),
        result_type="reviewed",
        status="finalized",
        total_score=Decimal("3"),
        max_score=Decimal("4"),
        confidence=Decimal("0.8000"),
        explanation_payload={},
    )
    review = TeacherReview(
        id=uuid.uuid4(),
        organization_id=run.organization_id,
        review_task_id=uuid.uuid4(),
        reviewer_id=uuid.uuid4(),
        grading_result_id=result.id,
        decision="approve",
        metadata_payload={},
    )

    payload = reviewed_example_payload(result=result, grading_run=run, teacher_review=review)

    assert payload["submission_id"] == str(run.submission_id)
    assert payload["teacher_decision"] == "approve"

    result.status = "needs_review"
    with pytest.raises(ValueError):
        reviewed_example_payload(result=result, grading_run=run)


def test_db_subject_pack_create_rejects_duplicate_global_key(db_session: Session) -> None:
    config = subject_pack_config()
    first = create_subject_pack(
        db_session,
        organization_id=None,
        key=f"python-pilot-{uuid.uuid4()}",
        name="Python Pilot",
        config=config,
    )

    resolved = resolve_active_subject_pack(db_session, key=first.key, organization_id=None)

    assert resolved is not None
    assert resolved.id == first.id
    with pytest.raises(SubjectPackValidationError, match="already exists"):
        create_subject_pack(
            db_session,
            organization_id=None,
            key=first.key,
            name="Duplicate Python Pilot",
            config=config,
        )


def test_db_review_queue_filters_and_orders_tasks(db_session: Session) -> None:
    organization = Organization(
        name=f"Pilot Review Org {uuid.uuid4()}",
        slug=f"pilot-review-{uuid.uuid4()}",
        status="active",
    )
    db_session.add(organization)
    db_session.flush()

    learner = Learner(
        organization_id=organization.id,
        external_ref=f"learner-{uuid.uuid4()}",
        display_name="Pilot Learner",
        status="active",
    )
    db_session.add(learner)
    db_session.flush()

    assessment_type = AssessmentType(
        organization_id=organization.id,
        key=f"pilot-review-{uuid.uuid4()}",
        name="Pilot Review",
        description="Synthetic pilot review type.",
        config={},
        status="active",
    )
    db_session.add(assessment_type)
    db_session.flush()

    assessment = Assessment(
        organization_id=organization.id,
        assessment_type_id=assessment_type.id,
        title="Pilot Review Assessment",
        status="active",
        settings={},
    )
    db_session.add(assessment)
    db_session.flush()

    submission = Submission(
        organization_id=organization.id,
        assessment_id=assessment.id,
        learner_id=learner.id,
        status="submitted",
        metadata_payload={},
    )
    db_session.add(submission)
    db_session.flush()

    low = ReviewTask(
        organization_id=organization.id,
        submission_id=submission.id,
        status="open",
        priority="low",
        confidence_band="low",
        escalation_reason="low_confidence",
        policy_payload={},
    )
    urgent = ReviewTask(
        organization_id=organization.id,
        submission_id=submission.id,
        status="open",
        priority="urgent",
        confidence_band="low",
        escalation_reason="policy_exception",
        policy_payload={"reason": "pilot"},
    )
    closed = ReviewTask(
        organization_id=organization.id,
        submission_id=submission.id,
        status="completed",
        priority="urgent",
        confidence_band="low",
        escalation_reason="completed",
        policy_payload={},
    )
    db_session.add_all([low, urgent, closed])
    db_session.flush()

    tasks = list_review_tasks(
        db_session,
        organization_id=organization.id,
        statuses={"open"},
        confidence_band="low",
    )

    assert [task.id for task in tasks] == [urgent.id, low.id]
    assert all(task.status == "open" for task in tasks)
