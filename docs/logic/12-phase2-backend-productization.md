# Phase 2 Backend Productization

This document describes the Phase 2 backend productization boundary for RubriCore-STE. It captures what is now reusable for later API, UI, job, and demo work without implementing a user-facing application.

## Implemented Boundary

Phase 2 now has three backend layers:

| Layer | Purpose |
| --- | --- |
| Service modules | Own business rules, persistence behavior, validation, versioning, and audit events |
| Pilot contracts | Define typed Pydantic request and response payloads for pilot workflows |
| Pilot workflows | Compose contracts and services into callable backend entry points |

The workflow facade lives in `app.pilot.workflows`.

It wraps:

- subject-pack creation and resolution
- answer-key draft creation, draft update, and publication
- review-task list summaries
- rubric draft updates
- fixture manifest validation
- grading-result export
- reviewed-example calibration payload export

## Why This Exists Before UI

The facade gives future FastAPI routes, background jobs, CLI tools, smoke scripts, and frontend adapters one stable backend place to call. This avoids duplicating service wiring across future phases.

It also keeps the project from treating early UI/API assumptions as core business logic. Grading, review, rubric immutability, answer-key versioning, and audit behavior remain in the service layer.

## Reuse Path

Future API route handlers should follow this pattern:

`route input -> pilot contract -> pilot workflow -> response contract`

Future UI work should call API routes that preserve the same payload shape, unless product requirements justify a versioned contract change.

## Completion Criteria For This Slice

This backend productization slice is complete when:

- pilot contracts validate public-safe payloads
- pilot workflows compose service calls without owning domain rules
- a smoke workflow proves the Phase 2 backend flow can be stitched together
- docs clearly say public API/UI are deferred
- tests, lint, and type checks pass

## Still Deferred

This slice intentionally does not add:

- FastAPI routes
- auth or permissions
- UI screens
- production pagination
- upload sessions
- external AI provider integration
- vector retrieval
- deployment packaging

