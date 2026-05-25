# Phase 2 Pilot API Plan

This document sketches the future API surface that can wrap the Phase 2 pilot contracts. It is a planning artifact, not an implemented HTTP API.

The intended shape is a thin adapter layer:

`HTTP route -> Pydantic pilot contract -> service function -> response contract`

Route handlers should not own grading, review, versioning, or audit behavior. Those rules remain in the service layer.

## Proposed Pilot Routes

| Workflow | Future route shape | Contract models | Service boundary |
| --- | --- | --- | --- |
| Create subject pack | `POST /pilot/subject-packs` | `SubjectPackCreateRequest`, `SubjectPackSummaryResponse` | `create_subject_pack`, `subject_pack_summary` |
| Resolve subject pack | `GET /pilot/subject-packs/{key}` | `SubjectPackSummaryResponse` | `resolve_active_subject_pack`, `subject_pack_summary` |
| Create answer key draft | `POST /pilot/answer-keys` | `AnswerKeyCreateRequest` | `create_answer_key` |
| Update answer key draft | `PATCH /pilot/answer-keys/{answer_key_id}/draft` | `AnswerKeyUpdateRequest` | `update_answer_key_draft` |
| Publish answer key | `POST /pilot/answer-keys/{answer_key_id}/versions` | `AnswerKeyPublishRequest`, `AnswerKeyVersionResponse` | `publish_answer_key_version` |
| List review tasks | `GET /pilot/review-tasks` | `ReviewTaskListRequest`, `ReviewTaskSummaryResponse` | `list_review_tasks`, `review_task_summary` |
| Update rubric draft | `PATCH /pilot/rubrics/{rubric_id}/draft` | `RubricDraftUpdateRequest` | `update_rubric_draft` |
| Validate fixture manifest | `POST /pilot/fixtures/manifest/validate` | `FixtureManifestRequest` | `validate_fixture_manifest` |
| Export grading result | `GET /pilot/grading-results/{grading_result_id}/export` | `GradingResultExportResponse` | `export_grading_result` |
| Export reviewed example | `GET /pilot/grading-results/{grading_result_id}/reviewed-example` | `ReviewedExamplePayloadResponse` | `reviewed_example_payload` |

## Smoke Workflow

The current end-to-end smoke workflow is covered by `test_phase_2_pilot_smoke_workflow_links_service_and_contract_payloads`.

It exercises this backend-only flow:

`subject pack -> answer key draft/publish -> rubric draft update -> review queue summary -> export/calibration payload`

This proves the pilot services and contracts can be composed before a real API or UI exists.

## Productization Rules

When these routes are implemented:

- Keep route handlers thin.
- Use the existing Pydantic contracts rather than ad hoc dictionaries.
- Preserve audit behavior in services.
- Do not mutate published rubric or answer-key versions.
- Do not add UI-specific workflow assumptions to service functions.
- Use `/pilot` or another clearly unstable prefix until the API is product-stable.
- Keep authentication, authorization, pagination, and upload sessions as explicit future slices.

## Deferred Work

This plan does not implement:

- FastAPI app setup
- public endpoint stability promises
- production auth or permissions
- upload sessions and object storage
- rich document parsing
- vector retrieval
- external AI provider integration
- teacher-facing UI screens

