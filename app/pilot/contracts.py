from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.services.pilot_io import validate_fixture_manifest


NonEmptyString = str
JsonObject = dict[str, Any]


class PilotContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiErrorResponse(PilotContract):
    code: str
    message: str
    details: JsonObject | list[JsonObject] | None = None


class ApiRouteSummaryResponse(PilotContract):
    method: str
    path: str
    request_contract: str | None = None
    response_contract: str | None = None
    auth_required: bool
    data_boundary: str


class SubjectPackCreateRequest(PilotContract):
    organization_id: uuid.UUID | None = None
    key: NonEmptyString
    name: NonEmptyString
    description: str | None = None
    config: JsonObject

    @field_validator("key", "name")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class SubjectPackSummaryResponse(PilotContract):
    id: str | None
    organization_id: str | None
    key: str
    name: str
    schema_version: str
    status: Literal["active", "archived"]
    assessment_types: list[str] = Field(default_factory=list)
    evidence_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    rubric_types: list[str] = Field(default_factory=list)


class AnswerKeyCreateRequest(PilotContract):
    organization_id: uuid.UUID
    assessment_item_id: uuid.UUID
    title: NonEmptyString
    draft_key: JsonObject
    created_by_user_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Answer key title must not be blank.")
        return value


class AnswerKeyUpdateRequest(PilotContract):
    draft_key: JsonObject


class AnswerKeyPublishRequest(PilotContract):
    published_by_user_id: uuid.UUID | None = None
    reason: str | None = None
    request_id: str | None = None


class AnswerKeyVersionResponse(PilotContract):
    answer_key_id: str
    answer_key_version_id: str | None
    version_number: int
    status: Literal["published", "archived"]


class ReviewTaskListRequest(PilotContract):
    organization_id: uuid.UUID
    statuses: set[Literal["open", "assigned", "completed", "cancelled"]] | None = None
    assigned_reviewer_id: uuid.UUID | None = None
    assessment_id: uuid.UUID | None = None
    assessment_item_id: uuid.UUID | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    confidence_band: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class ReviewTaskSummaryResponse(PilotContract):
    id: str | None
    organization_id: str
    assessment_id: str | None
    assessment_item_id: str | None
    submission_id: str
    grading_run_id: str | None
    grading_result_id: str | None
    assigned_reviewer_id: str | None
    status: Literal["open", "assigned", "completed", "cancelled"]
    priority: Literal["low", "normal", "high", "urgent"]
    confidence_band: str | None
    escalation_reason: str
    policy_payload: JsonObject


class RubricDraftUpdateRequest(PilotContract):
    draft_schema: JsonObject
    actor_user_id: uuid.UUID | None = None
    actor_source: Literal["teacher", "system", "fixture_import", "api_import"] = "teacher"
    title: str | None = None
    description: str | None = None
    metadata_patch: JsonObject | None = None
    reason: str | None = None
    request_id: str | None = None


class FixtureFileEntry(PilotContract):
    path: NonEmptyString
    purpose: NonEmptyString
    description: NonEmptyString

    @field_validator("path", "purpose", "description")
    @classmethod
    def require_file_entry_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Fixture file fields must not be blank.")
        return value


class FixtureManifestRequest(PilotContract):
    fixture_set: NonEmptyString
    title: NonEmptyString
    privacy: Literal["public_safe"]
    files: list[FixtureFileEntry] = Field(min_length=1)

    @field_validator("fixture_set", "title")
    @classmethod
    def require_manifest_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Manifest fields must not be blank.")
        return value

    def validation_errors(self) -> list[str]:
        return validate_fixture_manifest(self.model_dump())


class FixtureManifestValidationResponse(PilotContract):
    validation_errors: list[str]


class EvaluationBaselineRequest(PilotContract):
    manifest: JsonObject


class EvaluationBaselineResponse(PilotContract):
    validation_errors: list[str]
    report: JsonObject | None = None


class GradingRunRequest(PilotContract):
    submission_id: uuid.UUID
    rubric_version_id: uuid.UUID | None = None
    answer_key_version_id: uuid.UUID | None = None
    selected_levels_by_criterion: dict[str, str] = Field(default_factory=dict)
    ai_allowed: bool = True
    ai_required: bool = False
    auto_finalize_allowed: bool = True
    mandatory_review: bool = False
    answer_key_required: bool = False
    confidence_threshold: Decimal = Field(default=Decimal("0.85"), ge=0, le=1)
    review_threshold: Decimal = Field(default=Decimal("0.70"), ge=0, le=1)
    reason: str | None = None
    request_id: str | None = None


class ReviewActionRequest(PilotContract):
    reason: NonEmptyString
    feedback: str | None = None
    total_score: Decimal | None = Field(default=None, ge=0)
    criterion_result_id: uuid.UUID | None = None
    criterion_key: str | None = None
    criterion_score: Decimal | None = Field(default=None, ge=0)
    criterion_max_score: Decimal | None = Field(default=None, ge=0)
    criterion_explanation: str | None = None
    request_id: str | None = None

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Teacher review actions require a reason.")
        return value


class GradingResultExportResponse(PilotContract):
    grading_result_id: str | None
    grading_run_id: str
    rubric_version_id: str | None
    answer_key_version_id: str | None
    result_type: str
    status: str
    total_score: Decimal | None
    max_score: Decimal | None
    confidence: Decimal | None
    feedback: str | None
    explanation_payload: JsonObject
    criterion_results: list["CriterionResultResponse"] = Field(default_factory=list)


class CriterionResultResponse(PilotContract):
    id: str | None
    criterion_key: str
    source: str
    score: Decimal | None
    max_score: Decimal | None
    confidence: Decimal | None
    explanation: str | None
    metadata_payload: JsonObject


class ReviewedExamplePayloadResponse(PilotContract):
    grading_result_id: str | None
    grading_run_id: str
    submission_id: str | None
    rubric_version_id: str | None
    answer_key_version_id: str | None
    result_type: str
    status: Literal["finalized"]
    total_score: Decimal | None
    max_score: Decimal | None
    confidence: Decimal | None
    teacher_decision: str | None
    teacher_review_id: str | None
    metadata: JsonObject


class AIInteractionSummaryResponse(PilotContract):
    id: str | None
    provider: str
    model: str
    validation_status: Literal["pending", "valid", "invalid", "failed"]
    error_message: str | None = None


class GradingRunResponse(PilotContract):
    grading_run_id: str
    grading_run_status: str
    grading_result: GradingResultExportResponse | None
    review_task_id: str | None = None
    ai_interaction: AIInteractionSummaryResponse | None = None


class ReviewActionResponse(PilotContract):
    review_task: ReviewTaskSummaryResponse
    grading_result: GradingResultExportResponse
    teacher_review_id: str | None
    decision: str
    teacher_override_id: str | None = None
    regrade_run_id: str | None = None
    actionable: bool


class DemoGradingContextResponse(PilotContract):
    actor_user_id: str
    organization_id: str
    role: Literal["teacher"]
    submission_id: str
    rubric_version_id: str
    answer_key_version_id: str | None = None
