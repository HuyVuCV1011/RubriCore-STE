import uuid
from decimal import Decimal

import pytest

from app.db.models import (
    AnswerKey,
    AuditEvent,
    GradingResult,
    GradingRun,
    ReviewTask,
    Rubric,
    SubjectPack,
    TeacherReview,
)
from app.pilot.contracts import (
    AnswerKeyCreateRequest,
    AnswerKeyPublishRequest,
    AnswerKeyUpdateRequest,
    FixtureManifestRequest,
    ReviewTaskListRequest,
    RubricDraftUpdateRequest,
    SubjectPackCreateRequest,
)
from app.pilot.workflows import (
    PilotWorkflowError,
    create_answer_key_workflow,
    create_subject_pack_workflow,
    export_grading_result_workflow,
    list_review_task_summaries_workflow,
    publish_answer_key_workflow,
    resolve_subject_pack_workflow,
    reviewed_example_payload_workflow,
    update_answer_key_draft_workflow,
    update_rubric_draft_workflow,
    validate_fixture_manifest_workflow,
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


def subject_pack_config() -> dict:
    return {
        "schema_version": "1.0",
        "assessment_types": ["code-assignment"],
        "evidence_types": ["code"],
        "output_types": ["executable-behavior"],
        "rubric_types": ["analytic-rubric"],
    }


def rubric_schema() -> dict:
    return {
        "schema_version": "1.0",
        "criteria": [{"key": "correctness", "label": "Correctness", "position": 0, "weight": "1"}],
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


def test_subject_pack_workflows_create_and_resolve_summary_contracts() -> None:
    organization_id = uuid.uuid4()
    session = RecordingSession()

    created = create_subject_pack_workflow(
        session,  # type: ignore[arg-type]
        SubjectPackCreateRequest(
            organization_id=organization_id,
            key="python-pilot",
            name="Python Pilot",
            config=subject_pack_config(),
        ),
    )

    assert created.organization_id == str(organization_id)
    assert created.key == "python-pilot"

    existing_pack = records(session, SubjectPack)[0]
    resolve_session = RecordingSession(scalar_results=[existing_pack])
    resolved = resolve_subject_pack_workflow(
        resolve_session,  # type: ignore[arg-type]
        key="python-pilot",
        organization_id=organization_id,
    )

    assert resolved.id == str(existing_pack.id)
    with pytest.raises(PilotWorkflowError):
        resolve_subject_pack_workflow(
            RecordingSession(),  # type: ignore[arg-type]
            key="missing",
            organization_id=organization_id,
        )


def test_answer_key_workflows_create_update_publish_and_return_version_contract() -> None:
    session = RecordingSession()
    answer_key = create_answer_key_workflow(
        session,  # type: ignore[arg-type]
        AnswerKeyCreateRequest(
            organization_id=uuid.uuid4(),
            assessment_item_id=uuid.uuid4(),
            title="Pilot Answer Key",
            draft_key={"accepted": ["42"]},
        ),
    )

    update_answer_key_draft_workflow(
        session,  # type: ignore[arg-type]
        answer_key=answer_key,
        request=AnswerKeyUpdateRequest(draft_key={"accepted": ["42", "forty-two"]}),
    )
    published = publish_answer_key_workflow(
        session,  # type: ignore[arg-type]
        answer_key=answer_key,
        request=AnswerKeyPublishRequest(reason="Pilot publish."),
    )

    assert records(session, AnswerKey) == [answer_key]
    assert answer_key.status == "published"
    assert published.answer_key_id == str(answer_key.id)
    assert published.version_number == 1
    assert records(session, AuditEvent)[0].action == "answer_key_version.published"


def test_review_rubric_export_and_calibration_workflows_return_contracts() -> None:
    organization_id = uuid.uuid4()
    submission_id = uuid.uuid4()
    review_task = ReviewTask(
        id=uuid.uuid4(),
        organization_id=organization_id,
        submission_id=submission_id,
        status="open",
        priority="urgent",
        confidence_band="low",
        escalation_reason="low_confidence",
        policy_payload={"source": "workflow_test"},
    )
    review_session = RecordingSession(scalars_results=[review_task])

    review_summaries = list_review_task_summaries_workflow(
        review_session,  # type: ignore[arg-type]
        ReviewTaskListRequest(organization_id=organization_id, statuses={"open"}, limit=10),
    )

    rubric = Rubric(
        id=uuid.uuid4(),
        organization_id=organization_id,
        rubric_type_id=uuid.uuid4(),
        title="Original Rubric",
        status="published",
        draft_schema=rubric_schema(),
        latest_version_number=1,
        metadata_payload={},
    )
    rubric_session = RecordingSession()
    updated_rubric = update_rubric_draft_workflow(
        rubric_session,  # type: ignore[arg-type]
        rubric=rubric,
        request=RubricDraftUpdateRequest(
            draft_schema=rubric_schema(),
            title="Updated Rubric",
            metadata_patch={"source": "workflow_test"},
            reason="Pilot workflow.",
        ),
    )

    grading_run = GradingRun(
        id=uuid.uuid4(),
        organization_id=organization_id,
        submission_id=submission_id,
        status="completed",
        context_payload={},
    )
    grading_result = GradingResult(
        id=uuid.uuid4(),
        organization_id=organization_id,
        grading_run_id=grading_run.id,
        rubric_version_id=uuid.uuid4(),
        result_type="reviewed",
        status="finalized",
        total_score=Decimal("4"),
        max_score=Decimal("5"),
        confidence=Decimal("0.8500"),
        feedback="Good work.",
        explanation_payload={"source": "workflow_test"},
    )
    teacher_review = TeacherReview(
        id=uuid.uuid4(),
        organization_id=organization_id,
        review_task_id=review_task.id,
        reviewer_id=uuid.uuid4(),
        grading_result_id=grading_result.id,
        decision="approve",
        metadata_payload={},
    )

    exported = export_grading_result_workflow(grading_result)
    reviewed_example = reviewed_example_payload_workflow(
        result=grading_result,
        grading_run=grading_run,
        teacher_review=teacher_review,
    )

    assert review_summaries[0].priority == "urgent"
    assert updated_rubric.status == "draft"
    assert updated_rubric.metadata_payload == {"source": "workflow_test"}
    assert exported.total_score == Decimal("4")
    assert reviewed_example.teacher_decision == "approve"
    assert reviewed_example.submission_id == str(submission_id)


def test_fixture_manifest_workflow_returns_public_safe_errors() -> None:
    manifest = FixtureManifestRequest.model_validate(
        {
            "fixture_set": "demo",
            "title": "Demo",
            "privacy": "public_safe",
            "files": [
                {
                    "path": "../private.txt",
                    "purpose": "assessment_material",
                    "description": "Invalid path.",
                }
            ],
        }
    )

    assert validate_fixture_manifest_workflow(manifest) == [
        "File entry 0 path must be relative and stay inside fixture root."
    ]
