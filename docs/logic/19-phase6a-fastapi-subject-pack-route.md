# Phase 6A FastAPI Subject-Pack Route

This document records the first FastAPI-backed route and dependency shape for RubriCore-STE.

Phase 6A adds FastAPI deliberately because the project is now crossing from public-safe, DB-free pilot routes into the first auth-aware DB-backed HTTP route. It keeps the route read-only and low risk.

## Implemented Boundary

The FastAPI app lives in `app.pilot.fastapi_app`.

Implemented routes:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/pilot/health` | FastAPI health check |
| `POST` | `/pilot/fixtures/manifest/validate` | Public-safe fixture manifest validation through existing adapter |
| `POST` | `/pilot/evaluation/public-baseline` | Public-safe baseline report through existing adapter |
| `GET` | `/pilot/subject-packs/{key}` | First auth-aware DB-backed read-only route |

The stdlib pilot HTTP boundary remains available for local smoke use. FastAPI is the production-route shape going forward.

## Dependency Shape

DB-backed FastAPI routes use dependencies for:

- auth context: `get_pilot_auth_context`
- database session: `get_fastapi_db`

The current auth dependency reads explicit pilot headers:

- `X-Pilot-Actor-User-Id`
- `X-Pilot-Organization-Id`
- `X-Pilot-Roles`
- `X-Pilot-Request-Id`

These headers are a development boundary for wiring and tests. They are not production authentication. A future auth provider should replace `get_pilot_auth_context` with token/session verification while preserving the route dependency shape.

## Subject-Pack Loading

The subject-pack route uses `load_subject_pack_for_context` from `app.pilot.db_loaders`.

The loader:

- requires `read_subject_packs`
- resolves an active subject pack for the request organization
- allows a global active pack fallback
- checks same-tenant access for organization-owned packs
- returns `None` for missing packs instead of leaking cross-tenant resource existence

The route returns only `SubjectPackSummaryResponse`.

## Error Envelope

FastAPI routes use the same response posture as the pilot HTTP boundary:

```json
{
  "error": {
    "code": "not_found",
    "message": "Subject pack was not found.",
    "details": null
  }
}
```

Handled errors include:

- missing auth context: `401 missing_auth_context`
- invalid auth context: `401 invalid_auth_context`
- permission failure: `403 forbidden`
- missing subject pack: `404 not_found`
- request validation failure: `422 validation_error`

## Still Deferred

Phase 6A does not add:

- production OAuth/OIDC/JWT verification
- sessions or API keys
- user or membership lookup
- review queue routes
- grading-result export routes
- calibration export routes
- answer-key mutation routes
- rubric draft mutation routes
- UI
- provider calls
- rich upload/import
- vector retrieval
- schema changes

## Acceptance Criteria

Phase 6A is complete when:

- FastAPI and test client dependencies are explicit and locked
- the FastAPI app exposes public-safe adapter routes and one DB-backed subject-pack route
- subject-pack route requires auth context
- subject-pack route uses tenant-scoped loading and permission checks
- tests cover missing auth, successful tenant access, global fallback, not found, and missing permission
- full tests, lint, type checks, and public-safe smoke pass
