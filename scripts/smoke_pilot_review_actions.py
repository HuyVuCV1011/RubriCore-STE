from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.pilot.fastapi_app import create_app  # noqa: E402


def main() -> None:
    summary = run_pilot_review_action_smoke()
    print(json.dumps(summary, indent=2, sort_keys=True))


def run_pilot_review_action_smoke() -> dict[str, Any]:
    client = TestClient(create_app())

    health = client.get("/pilot/health")
    _require_status(health.status_code, 200, "health", _response_json(health))

    sample = client.get("/pilot/demo/sample-grading-context")
    sample_body = _response_json(sample)
    _require_status(sample.status_code, 200, "sample grading context", sample_body)

    headers = _pilot_headers(sample_body, request_id="smoke-pilot-review-actions-grading")
    grading = client.post(
        "/pilot/grading-runs",
        headers=headers,
        json={
            "submission_id": sample_body["submission_id"],
            "rubric_version_id": sample_body["rubric_version_id"],
            "answer_key_version_id": sample_body.get("answer_key_version_id"),
            "ai_allowed": True,
            "auto_finalize_allowed": True,
            "mandatory_review": True,
            "request_id": "smoke-pilot-review-actions-grading",
        },
    )
    grading_body = _response_json(grading)
    _require_status(grading.status_code, 200, "grading run", grading_body)

    review_task_id = grading_body.get("review_task_id")
    result = grading_body.get("grading_result") or {}
    if not review_task_id or result.get("status") != "needs_review":
        raise SystemExit(f"Grading did not produce an actionable review task: {grading_body}")

    action = client.post(
        f"/pilot/review-tasks/{review_task_id}/actions/approve",
        headers=_pilot_headers(sample_body, request_id="smoke-pilot-review-actions-approve"),
        json={
            "reason": "Smoke test approves a mandatory-review grading result.",
            "request_id": "smoke-pilot-review-actions-approve",
        },
    )
    action_body = _response_json(action)
    _require_status(action.status_code, 200, "approve review action", action_body)

    action_result = action_body.get("grading_result") or {}
    action_task = action_body.get("review_task") or {}
    if action_body.get("decision") != "approve":
        raise SystemExit(f"Approve action returned an unexpected decision: {action_body}")
    if action_task.get("status") != "completed":
        raise SystemExit(f"Review task was not completed: {action_body}")
    if action_result.get("status") != "finalized" or action_result.get("result_type") != "reviewed":
        raise SystemExit(f"Grading result was not finalized as reviewed: {action_body}")

    return {
        "health": health.json(),
        "sample": {
            "organization_id": sample_body["organization_id"],
            "submission_id": sample_body["submission_id"],
            "rubric_version_id": sample_body["rubric_version_id"],
        },
        "grading": {
            "grading_run_id": grading_body["grading_run_id"],
            "review_task_id": review_task_id,
            "grading_result_id": result.get("grading_result_id"),
            "result_status": result.get("status"),
            "ai_provider": (grading_body.get("ai_interaction") or {}).get("provider"),
            "ai_validation_status": (grading_body.get("ai_interaction") or {}).get("validation_status"),
        },
        "review_action": {
            "decision": action_body["decision"],
            "review_task_status": action_task.get("status"),
            "grading_result_status": action_result.get("status"),
            "grading_result_type": action_result.get("result_type"),
            "teacher_review_id": action_body.get("teacher_review_id"),
        },
    }


def _pilot_headers(sample_body: dict[str, Any], *, request_id: str) -> dict[str, str]:
    return {
        "X-Pilot-Actor-User-Id": sample_body["actor_user_id"],
        "X-Pilot-Organization-Id": sample_body["organization_id"],
        "X-Pilot-Roles": sample_body["role"],
        "X-Pilot-Request-Id": request_id,
    }


def _response_json(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise SystemExit(f"Response was not JSON: {response.text}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object response: {payload}")
    return payload


def _require_status(status_code: int, expected: int, label: str, body: dict[str, Any]) -> None:
    if status_code != expected:
        raise SystemExit(f"{label} returned HTTP {status_code}: {body}")


if __name__ == "__main__":
    main()
