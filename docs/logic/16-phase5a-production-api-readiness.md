# Phase 5A Production API Readiness

This document records the Phase 5A framework decision and structural API readiness work after the Phase 4 pilot HTTP boundary.

Phase 5A is intentionally boring. It does not expand product functionality. It makes the existing pilot API boundary easier to replace, wrap, or promote later without moving business logic into transport code.

## Framework Decision

RubriCore-STE should keep the current dependency-free stdlib pilot HTTP boundary for now.

Do not add FastAPI yet.

FastAPI becomes worth adding when the project is ready to implement at least one of these production concerns:

- production authentication and authorization
- tenant-aware database object loading
- OpenAPI generation as a product contract
- dependency-injected database sessions and request context
- middleware for request IDs, CORS, logging, and error policy
- deployed API packaging and operational health checks

Until then, the stdlib boundary is enough for local smoke validation and protects the repo from treating pilot routes as production product surface.

## Implemented Phase 5A Structure

Phase 5A adds structural readiness on top of Phase 4:

| Area | Implemented shape |
| --- | --- |
| Error responses | Stable JSON envelope with `error.code`, `error.message`, and optional `error.details` |
| Route metadata | `/pilot/routes` returns method, path, request contract, response contract, auth posture, and data boundary |
| Framework posture | Docs explicitly defer FastAPI until auth, tenancy, OpenAPI, and deployment needs justify it |
| Public-safe smoke | Existing smoke path remains public-fixture-only and dependency-free |

## Current Public Pilot Routes

| Method | Path | Contract boundary | Auth posture | Data boundary |
| --- | --- | --- | --- | --- |
| `GET` | `/pilot/health` | Transport-only health payload | No production auth | No data access |
| `GET` | `/pilot/routes` | Route metadata payload | No production auth | No data access |
| `POST` | `/pilot/fixtures/manifest/validate` | `FixtureManifestRequest` -> `FixtureManifestValidationResponse` | No production auth | Caller-provided public-safe manifest |
| `POST` | `/pilot/evaluation/public-baseline` | `EvaluationBaselineRequest` -> `EvaluationBaselineResponse` | No production auth | Caller-provided public-safe manifest |

## Error Envelope

Transport errors use this shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request body failed contract validation.",
    "details": []
  }
}
```

The pilot boundary currently maps:

| Condition | Status | Code |
| --- | --- | --- |
| Unknown route | `404` | `not_found` |
| Known path with wrong method | `405` | `method_not_allowed` |
| Invalid JSON | `400` | `invalid_json` |
| Contract validation failure | `422` | `validation_error` |
| Bad JSON object shape | `400` | `bad_request` |

Domain validation still belongs in service and contract logic. For example, public-safe fixture marker checks return normal validation payloads from the fixture-validation route rather than transport errors.

## Still Deferred

Phase 5A does not add:

- FastAPI or another web framework
- production auth or permissions
- tenant-aware object loading
- DB-backed routes
- OpenAPI contract generation
- UI
- provider calls or prompt execution
- rich import/upload
- vector retrieval
- private fixture loading
- schema changes
- dependency changes

## Acceptance Criteria

Phase 5A is complete when:

- the framework decision is documented
- pilot HTTP errors use a stable response envelope
- route metadata exposes contract, auth, and data-boundary posture
- tests cover the error envelope and route metadata
- Phase 4 smoke still passes
- full tests, lint, and type checks pass

## Next Phase

The next phase is [Phase 5B auth and tenancy design](17-phase5b-auth-tenancy-design.md). Do not expose review queues, grading-result lookup by ID, subject-pack resolution, rubric drafts, answer-key mutation, or calibration exports over HTTP until request identity, organization boundaries, object-loading rules, and audit expectations are implemented.
