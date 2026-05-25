# Phase 2 Pilot Contracts

This document describes the public Phase 2 pilot contract layer for RubriCore-STE. It focuses on stable Python/Pydantic payload shapes that can later be reused by API routes, background jobs, command-line tools, or a teacher-facing UI.

The pilot contracts are not a finished public API and are not a user-facing application. They are a narrow boundary around the current backend services so later phases can reuse request and response shapes without moving business rules into routes or screens.

## Purpose

The contract layer gives Phase 2 workflows a typed handoff point between callers and backend services.

Current contracts cover:

- subject-pack creation and summary payloads
- answer-key draft, update, and publish payloads
- review-queue filter and summary payloads
- rubric draft update payloads
- public-safe fixture manifest validation
- grading-result export payloads
- reviewed-example calibration payloads

## Boundary

Contracts validate shape, required fields, allowed enum values, and pilot-safe limits. They do not own business behavior.

Business rules remain in service modules:

- `app.db.services.subject_packs`
- `app.db.services.answer_keys`
- `app.db.services.review_queue`
- `app.db.services.rubric_authoring`
- `app.db.services.pilot_io`
- `app.db.services.calibration`

For example, `ReviewTaskListRequest` validates that `priority` is one of the known review priorities and that `limit` is within the pilot range. The actual database query and ordering remain in `list_review_tasks`.

## Reuse In Later Phases

Later API or UI work can reuse these contracts as adapter payloads. A route handler should:

1. Validate the incoming payload with a contract model.
2. Call the relevant service function.
3. Convert service summaries or export dictionaries into response contracts.

This keeps route handlers thin and prevents UI workflow assumptions from leaking into grading, review, versioning, or audit logic.

## Stability

These contracts are pilot-stable but not final product-stable. They are safe for internal development, demos, smoke workflows, and future API planning. They should not yet be advertised as a permanent public HTTP API.

Breaking changes should be small, documented, and covered by tests.

## Non-Goals

This slice does not add:

- FastAPI route handlers
- authentication or authorization
- production pagination
- upload sessions
- object storage integration
- vector retrieval
- external AI provider calls
- UI screens

Those remain later productization work.

