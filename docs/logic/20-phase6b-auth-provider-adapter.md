# Phase 6B Auth Provider Adapter

This document records the first production-auth adapter boundary in code.

Phase 6B does not add a real auth provider. It moves the existing development pilot-header behavior behind a narrow provider interface so future production auth can replace request verification without moving token, session, or membership logic into route handlers.

## Implemented Boundary

The provider scaffold lives in `app.pilot.auth_provider`.

| Concept | Implemented shape |
| --- | --- |
| Provider interface | `AuthProvider.verify_request(headers) -> PilotAuthContext` |
| Development implementation | `PilotHeaderAuthProvider` |
| Provider error | `PilotAuthProviderError` with stable API error code and message |
| FastAPI dependency | `get_pilot_auth_context` calls the provider and returns `PilotAuthContext` |

The interface is intentionally framework-light. FastAPI passes request headers to the provider, but the provider itself only depends on a plain mapping and the existing `PilotAuthContext`/`PilotRole` policy types.

## Pilot Header Provider

`PilotHeaderAuthProvider` preserves the Phase 6A development behavior:

- requires `X-Pilot-Actor-User-Id`
- requires `X-Pilot-Organization-Id`
- requires `X-Pilot-Roles`
- accepts optional `X-Pilot-Request-Id`
- rejects malformed UUIDs
- rejects unknown roles
- rejects requests with no roles
- returns `PilotAuthContext`

These headers remain development and test wiring only. They are not production authentication.

## Future Production Auth Fit

A future real provider can implement the same `AuthProvider` interface and perform:

- OAuth/OIDC/JWT validation
- session verification
- scoped API-key verification for internal jobs
- user and membership lookup
- organization-scope resolution
- disabled-user or disabled-membership checks

That future provider should still return only `PilotAuthContext` to the route layer. Provider-specific claims, secrets, token payloads, and network clients should stay out of route handlers and service-layer authorization code.

## Still Deferred

Phase 6B does not add:

- OAuth/OIDC/JWT verification
- session cookies
- API-key issuance or verification
- secrets or credentials
- network calls
- user or membership lookup
- new dependencies
- new DB-backed routes
- schema changes or Alembic migrations
- changes to grading, review, rubric, or evaluation semantics

## Acceptance Criteria

Phase 6B is complete when:

- pilot-header parsing no longer lives in `app.pilot.fastapi_app`
- tests prove valid pilot headers create `PilotAuthContext`
- tests prove missing headers, malformed UUIDs, empty roles, and unknown roles are rejected
- the existing subject-pack route still uses auth context, tenant-scoped loading, and permission checks
- docs clearly state that no real provider or credential verification was added

## Next Phase

The next implementation-planning phase is [Phase 6C production auth provider selection](21-phase6c-production-auth-provider-selection.md). It should choose the first real provider style and document config, claim mapping, organization membership resolution, and failure modes before any token verification code is added.
