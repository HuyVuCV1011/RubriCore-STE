import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.db.models import CriterionResult, GradingResult, ReviewTask, RubricVersion, Submission, SubmissionEvidence
from app.pilot.fastapi_app import create_app, get_fastapi_db, get_ollama_grading_provider


class RecordingSession:
    def __init__(self, records: dict[tuple[object, object], object]) -> None:
        self.records = records
        self.added: list[object] = []
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        for record in self.added:
            if hasattr(record, "id") and record.id is None:
                record.id = uuid.uuid4()

    def get(self, entity: object, ident: object) -> object | None:
        return self.records.get((entity, ident))

    def scalar(self, _: object) -> object | None:
        return None

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


class FakeAIProvider:
    provider_name = "fake-ollama"
    model_name = "fake-local-model"

    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output

    def evaluate(self, _: dict[str, Any]) -> dict[str, Any]:
        return self.output


def test_fastapi_grading_run_route_invokes_local_ai_provider_and_commits_result() -> None:
    organization_id = uuid.uuid4()
    actor_user_id = uuid.uuid4()
    submission = make_submission(organization_id=organization_id)
    rubric = make_rubric_version(submission)
    session = RecordingSession({(Submission, submission.id): submission, (RubricVersion, rubric.id): rubric})
    app = create_app()
    app.dependency_overrides[get_fastapi_db] = lambda: session
    app.dependency_overrides[get_ollama_grading_provider] = lambda: FakeAIProvider(
        {
            "criterion_suggestions": [
                {
                    "criterion_key": "correctness",
                    "score": "2",
                    "confidence": "0.91",
                    "explanation": "The submitted evidence directly addresses the expected behavior.",
                    "evidence_references": [str(submission.evidence[0].id)],
                }
            ],
            "confidence": "0.91",
            "overall_feedback_draft": "Meets the rubric.",
        }
    )
    client = TestClient(app)

    response = client.post(
        "/pilot/grading-runs",
        headers=pilot_headers(actor_user_id=actor_user_id, organization_id=organization_id, roles="teacher"),
        json={
            "submission_id": str(submission.id),
            "rubric_version_id": str(rubric.id),
            "ai_allowed": True,
            "request_id": "phase6e-route-test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grading_run_status"] == "completed"
    assert body["grading_result"]["status"] == "finalized"
    assert body["grading_result"]["confidence"] == "0.91"
    assert body["ai_interaction"]["provider"] == "fake-ollama"
    assert body["ai_interaction"]["validation_status"] == "valid"
    assert session.commit_count == 1
    assert session.rollback_count == 0


def test_fastapi_pilot_ui_is_available() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/pilot/ui")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "RubriCore Pilot" in response.text
    assert "Teacher Review" in response.text
    assert "Criterion details" in response.text
    assert "Feedback draft" in response.text
    assert "Review reasons and blocking signals" in response.text
    assert "Raw JSON" in response.text
    assert "Auto-finalized" in response.text
    assert "Needs teacher review" in response.text
    assert "Teacher actions" in response.text
    assert "Approve result" in response.text
    assert "Edit feedback" in response.text
    assert "Adjust total score" in response.text
    assert "Adjust criterion score" in response.text
    assert "Return for regrade" in response.text
    assert "/pilot/grading-runs" in response.text
    assert "/pilot/review-tasks/" in response.text


def test_fastapi_review_action_route_approves_result_and_returns_updated_state() -> None:
    organization_id = uuid.uuid4()
    actor_user_id = uuid.uuid4()
    submission, grading_result, review_task = make_review_context(organization_id=organization_id)
    session = RecordingSession(
        {
            (Submission, submission.id): submission,
            (GradingResult, grading_result.id): grading_result,
            (ReviewTask, review_task.id): review_task,
        }
    )
    app = create_app()
    app.dependency_overrides[get_fastapi_db] = lambda: session
    client = TestClient(app)

    response = client.post(
        f"/pilot/review-tasks/{review_task.id}/actions/approve",
        headers=pilot_headers(actor_user_id=actor_user_id, organization_id=organization_id, roles="teacher"),
        json={"reason": "The automated result matches the rubric evidence.", "request_id": "approve-route-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "approve"
    assert body["actionable"] is False
    assert body["review_task"]["status"] == "completed"
    assert body["grading_result"]["status"] == "finalized"
    assert body["grading_result"]["result_type"] == "reviewed"
    assert body["teacher_review_id"] is not None
    assert session.commit_count == 1
    assert session.rollback_count == 0


def test_fastapi_review_action_route_adjusts_criterion_score() -> None:
    organization_id = uuid.uuid4()
    submission, grading_result, review_task = make_review_context(organization_id=organization_id)
    criterion = CriterionResult(
        id=uuid.uuid4(),
        organization_id=organization_id,
        grading_result_id=grading_result.id,
        criterion_key="correctness",
        source="ai",
        score=Decimal("1"),
        max_score=Decimal("2"),
        confidence=Decimal("0.61"),
        explanation="AI was uncertain.",
        metadata_payload={},
    )
    grading_result.criterion_results = [criterion]
    session = RecordingSession(
        {
            (Submission, submission.id): submission,
            (GradingResult, grading_result.id): grading_result,
            (ReviewTask, review_task.id): review_task,
            (CriterionResult, criterion.id): criterion,
        }
    )
    app = create_app()
    app.dependency_overrides[get_fastapi_db] = lambda: session
    client = TestClient(app)

    response = client.post(
        f"/pilot/review-tasks/{review_task.id}/actions/adjust-criterion-score",
        headers=pilot_headers(actor_user_id=uuid.uuid4(), organization_id=organization_id, roles="reviewer"),
        json={
            "reason": "Manual review found partial credit.",
            "criterion_result_id": str(criterion.id),
            "criterion_key": "correctness",
            "criterion_score": "1.5",
            "criterion_max_score": "2",
            "criterion_explanation": "Teacher accepted a partially correct approach.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "override"
    assert body["teacher_override_id"] is not None
    assert body["grading_result"]["status"] == "finalized"
    assert body["grading_result"]["result_type"] == "overridden"
    assert session.commit_count == 1


def test_fastapi_review_action_route_rejects_read_only_role() -> None:
    organization_id = uuid.uuid4()
    submission, grading_result, review_task = make_review_context(organization_id=organization_id)
    session = RecordingSession(
        {
            (Submission, submission.id): submission,
            (GradingResult, grading_result.id): grading_result,
            (ReviewTask, review_task.id): review_task,
        }
    )
    app = create_app()
    app.dependency_overrides[get_fastapi_db] = lambda: session
    client = TestClient(app)

    response = client.post(
        f"/pilot/review-tasks/{review_task.id}/actions/approve",
        headers=pilot_headers(actor_user_id=uuid.uuid4(), organization_id=organization_id, roles="read_only"),
        json={"reason": "Looks correct."},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert session.commit_count == 0


def test_fastapi_grading_run_route_rejects_read_only_role() -> None:
    organization_id = uuid.uuid4()
    submission = make_submission(organization_id=organization_id)
    rubric = make_rubric_version(submission)
    session = RecordingSession({(Submission, submission.id): submission, (RubricVersion, rubric.id): rubric})
    app = create_app()
    app.dependency_overrides[get_fastapi_db] = lambda: session
    client = TestClient(app)

    response = client.post(
        "/pilot/grading-runs",
        headers=pilot_headers(actor_user_id=uuid.uuid4(), organization_id=organization_id, roles="read_only"),
        json={"submission_id": str(submission.id), "rubric_version_id": str(rubric.id)},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert session.commit_count == 0


def pilot_headers(*, actor_user_id: uuid.UUID, organization_id: uuid.UUID, roles: str) -> dict[str, str]:
    return {
        "X-Pilot-Actor-User-Id": str(actor_user_id),
        "X-Pilot-Organization-Id": str(organization_id),
        "X-Pilot-Roles": roles,
        "X-Pilot-Request-Id": "phase6e-test",
    }


def make_submission(*, organization_id: uuid.UUID) -> Submission:
    submission = Submission(
        id=uuid.uuid4(),
        organization_id=organization_id,
        learner_id=uuid.uuid4(),
        assessment_item_id=uuid.uuid4(),
        status="submitted",
        metadata_payload={},
    )
    submission.evidence = [
        SubmissionEvidence(
            id=uuid.uuid4(),
            organization_id=organization_id,
            submission_id=submission.id,
            evidence_type_id=uuid.uuid4(),
            raw_text="The answer satisfies the expected behavior.",
            value_payload={},
            status="submitted",
        )
    ]
    return submission


def make_rubric_version(submission: Submission) -> RubricVersion:
    return RubricVersion(
        id=uuid.uuid4(),
        organization_id=submission.organization_id,
        rubric_id=uuid.uuid4(),
        version_number=1,
        title="Pilot Rubric",
        rubric_schema={
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
                    "narrative": "Does not satisfy the expected behavior.",
                },
                {
                    "criterion_key": "correctness",
                    "performance_level_key": "meets",
                    "narrative": "Satisfies the expected behavior.",
                },
            ],
        },
        status="published",
    )


def make_review_context(*, organization_id: uuid.UUID) -> tuple[Submission, GradingResult, ReviewTask]:
    submission = make_submission(organization_id=organization_id)
    submission.assessment_id = uuid.uuid4()
    grading_result = GradingResult(
        id=uuid.uuid4(),
        organization_id=organization_id,
        grading_run_id=uuid.uuid4(),
        rubric_version_id=uuid.uuid4(),
        answer_key_version_id=None,
        result_type="proposed",
        status="needs_review",
        total_score=Decimal("1"),
        max_score=Decimal("2"),
        confidence=Decimal("0.68"),
        feedback="Automated feedback draft.",
        explanation_payload={
            "routing": {"decision": "route_to_review", "reasons": ["confidence_below_threshold"]},
            "review_reasons": ["confidence_below_threshold"],
        },
    )
    grading_result.criterion_results = []
    review_task = ReviewTask(
        id=uuid.uuid4(),
        organization_id=organization_id,
        assessment_id=submission.assessment_id,
        assessment_item_id=submission.assessment_item_id,
        submission_id=submission.id,
        grading_run_id=grading_result.grading_run_id,
        grading_result_id=grading_result.id,
        status="open",
        priority="normal",
        confidence_band="medium",
        escalation_reason="confidence_below_threshold",
        policy_payload={"reasons": ["confidence_below_threshold"]},
    )
    return submission, grading_result, review_task
