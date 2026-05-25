# Phase 5C Production Auth Implementation Plan

This document plans how RubriCore-STE should create production auth context and tenant-scoped DB loading before any DB-backed HTTP route is exposed.

Phase 5C is a design path, not an implementation of login or a provider integration. It chooses the shape that future implementation should follow so security rules do not drift into individual route handlers.

## Decision

Use framework middleware or dependency injection to create a verified `PilotAuthContext` before DB-backed handlers run.

Do not let route handlers parse tokens, infer tenants, or authorize resources directly. Route handlers should receive a verified context and use tenant-scoped loader helpers that enforce organization boundaries before returning ORM objects to workflow code.

## Provider Style

RubriCore-STE should support an external identity provider later, but should not pick or integrate one in this slice.

Recommended provider posture:

| Provider style | Future fit | Notes |
| --- | --- | --- |
| OIDC/JWT bearer tokens | Best production default | Works with hosted identity providers and API clients; requires issuer, audience, JWKS, expiry, and claim validation |
| Session cookie | Useful for first-party teacher UI later | Requires CSRF posture, cookie settings, session lifecycle, and browser-specific security decisions |
| API key | Useful for internal jobs only | Should be scoped, revocable, audited, and separated from teacher/user auth |

The first production API implementation should prefer OIDC/JWT bearer tokens if RubriCore-STE needs externally hosted auth. If the first real UI is same-origin and server-rendered, a session-cookie adapter can be added later without changing service-layer authorization rules.

## Auth Context Creation

Future request flow:

`HTTP request -> auth middleware/dependency -> token/session verification -> identity lookup -> organization scope resolution -> PilotAuthContext -> route handler`

The verified context should include:

- `actor_user_id`
- `organization_id`
- roles
- request id
- optional provider subject and issuer in request metadata, not in service-layer domain models

Validation requirements:

- reject missing credentials for DB-backed routes
- verify token/session authenticity before trusting claims
- verify token expiry and audience when using JWT
- map provider claims to internal user and organization records
- reject ambiguous organization scope
- reject disabled users or memberships
- keep provider-specific claims out of route business logic

## Tenant-Scoped DB Loading

Future DB-backed routes must load tenant-owned resources through helpers that include organization scope in the query.

Do this:

`load_grading_result_for_org(db, organization_id=context.organization_id, grading_result_id=...)`

Do not do this:

`db.get(GradingResult, grading_result_id)` followed by returning the object.

Required loader behavior:

- query by resource id and `organization_id`
- return not found for missing or cross-tenant resources
- avoid revealing whether a cross-tenant id exists
- return a `TenantScopedResource` or equivalent policy input before workflow execution
- keep object loading separate from permission checks, but require both before service/workflow calls

## Authorization Flow

Future DB-backed route flow:

`verified context -> tenant-scoped load -> permission check -> service/workflow -> response contract`

Use `app.pilot.authz` as the policy source:

- `PilotAuthContext` is the route-level identity boundary
- `TenantScopedResource` describes the loaded resource
- `authorize_tenant_resource` checks same-tenant access and required permission
- `DB_BACKED_ROUTE_PERMISSIONS` maps route templates to required permissions

Route handlers should not hard-code role names. They should ask the policy layer for permissions.

## Audit And Request IDs

Production auth implementation should create or accept a request id before route logic starts.

Audit expectations:

- mutation routes must preserve actor, organization, resource id, action, and request id
- tenant-owned export routes should audit who exported which resource
- denied auth attempts should be observable in operational logs without writing private payloads into tracked fixtures or public docs
- service-layer audit behavior should remain the source of truth for domain state changes

## First DB-Backed Route Candidate

After production auth context exists, the first DB-backed route should be read-only and low mutation risk.

Recommended candidate:

`GET /pilot/subject-packs/{key}`

Why:

- subject-pack summary shape already exists
- read-only route
- clear organization scope
- lower sensitivity than review queues, grading exports, calibration exports, answer-key mutation, or rubric draft mutation

Acceptance criteria for this first route:

- uses verified `PilotAuthContext`
- loads subject pack by key and organization scope
- supports only same-organization access, plus explicitly documented global-pack behavior if enabled
- checks `read_subject_packs`
- returns only `SubjectPackSummaryResponse`
- does not expose private fixtures, prompts, student data, or provider data
- has tests for same-tenant access, cross-tenant not-found/denied behavior, missing permission, and missing auth context

## Still Blocked

Do not expose these routes until the first auth-backed route is proven:

- review queue routes
- grading result export by id
- reviewed calibration export by id
- answer-key mutation
- rubric draft mutation
- private fixture loading
- provider or prompt execution
- rich upload/import
- vector retrieval

These routes involve more sensitive data, mutation, export, provider, or private-data boundaries.

## Dependency Decision

Adding FastAPI or another framework is reasonable when implementing production auth context because middleware/dependency injection, OpenAPI, and request state become useful at that point.

Do not add a framework just to keep adding public-safe DB-free routes. The stdlib pilot boundary remains enough for current smoke behavior.

## Follow-On

Phase 6A implements this candidate as a FastAPI route and preserves the dependency boundary described here. See [Phase 6A FastAPI Subject-Pack Route](19-phase6a-fastapi-subject-pack-route.md).

## Acceptance Criteria

Phase 5C is complete when:

- auth context creation flow is documented
- provider style options and recommended first provider posture are documented
- tenant-scoped DB loading rules are documented
- first DB-backed route candidate and acceptance criteria are documented
- README links the plan
- tests verify the plan remains discoverable
