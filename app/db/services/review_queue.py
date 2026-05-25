from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ReviewTask


PRIORITY_RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def list_review_tasks(
    db: Session,
    *,
    organization_id: uuid.UUID,
    statuses: set[str] | None = None,
    assigned_reviewer_id: uuid.UUID | None = None,
    assessment_id: uuid.UUID | None = None,
    assessment_item_id: uuid.UUID | None = None,
    priority: str | None = None,
    confidence_band: str | None = None,
    limit: int = 50,
) -> list[ReviewTask]:
    statement = select(ReviewTask).where(ReviewTask.organization_id == organization_id)
    if statuses:
        statement = statement.where(ReviewTask.status.in_(statuses))
    if assigned_reviewer_id is not None:
        statement = statement.where(ReviewTask.assigned_reviewer_id == assigned_reviewer_id)
    if assessment_id is not None:
        statement = statement.where(ReviewTask.assessment_id == assessment_id)
    if assessment_item_id is not None:
        statement = statement.where(ReviewTask.assessment_item_id == assessment_item_id)
    if priority is not None:
        statement = statement.where(ReviewTask.priority == priority)
    if confidence_band is not None:
        statement = statement.where(ReviewTask.confidence_band == confidence_band)

    tasks = list(db.scalars(statement))
    return sorted(
        tasks,
        key=lambda task: (PRIORITY_RANK.get(task.priority, 99), task.created_at or datetime.min.replace(tzinfo=UTC)),
    )[:limit]


def review_task_summary(task: ReviewTask) -> dict[str, Any]:
    return {
        "id": str(task.id) if task.id is not None else None,
        "organization_id": str(task.organization_id),
        "assessment_id": str(task.assessment_id) if task.assessment_id is not None else None,
        "assessment_item_id": str(task.assessment_item_id) if task.assessment_item_id is not None else None,
        "submission_id": str(task.submission_id),
        "grading_run_id": str(task.grading_run_id) if task.grading_run_id is not None else None,
        "grading_result_id": str(task.grading_result_id) if task.grading_result_id is not None else None,
        "assigned_reviewer_id": str(task.assigned_reviewer_id) if task.assigned_reviewer_id is not None else None,
        "status": task.status,
        "priority": task.priority,
        "confidence_band": task.confidence_band,
        "escalation_reason": task.escalation_reason,
        "policy_payload": task.policy_payload,
    }
