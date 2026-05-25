# Phase 5B Auth And Tenancy Design

This document defines the auth and tenancy boundary required before RubriCore-STE exposes any DB-backed workflow over HTTP.

Phase 5B is a design and guardrail slice. It does not implement production login, token verification, sessions, OAuth, SSO, API keys, or a production authorization provider. It defines the internal policy shape future HTTP routes must satisfy.

## Goal

Before exposing DB-backed routes, RubriCore-STE needs a clear answer for:

- who is making the request
- which organization/tenant the request is scoped to
- which roles and permissions the actor has
- whether the loaded resource belongs to the same organization
- whether the action should be audited
- which private/local data remains inaccessible from public pilot routes

No DB-backed HTTP route should be added until those checks are implemented at the route boundary or framework middleware layer.

## Implemented Design Boundary

The policy scaffold lives in `app.pilot.authz`.

| Concept | Implemented shape |
| --- | --- |
| Auth context | `PilotAuthContext` with actor user, organization, roles, and request id |
| Tenant resource | `TenantScopedResource` with organization, resource type, and optional resource id |
| Roles | `system`, `admin`, `teacher`, `reviewer`, `read_only` |
| Permissions | read subject packs, read grading exports, read review queue, write answer keys, write rubric drafts, export calibration |
| Tenant check | `require_same_tenant` rejects cross-organization access |
| Permission check | `require_permission` and `authorize_tenant_resource` reject missing role capability |
| DB route guard | `require_db_route_readiness` blocks DB-backed HTTP exposure without auth context and route policy |

This is intentionally pure Python and dependency-free.

## Role And Permission Posture

| Role | Intended capability |
| --- | --- |
| `system` | Internal trusted jobs after explicit implementation |
| `admin` | Full tenant-scoped access after production auth exists |
| `teacher` | Read grading/review context, write answer keys and rubric drafts, export calibration |
| `reviewer` | Read review queue and grading exports, export reviewed calibration examples |
| `read_only` | Read subject-pack summaries and grading exports only |

Roles are not global permissions to bypass tenancy. Every DB-backed object loaded for an HTTP route must still be checked against the request organization.

## DB-Backed Route Policy

The following route groups remain blocked from HTTP exposure until production auth context, object loading, tenancy checks, and audit behavior are implemented:

| Future route template | Required permission |
| --- | --- |
| `/pilot/subject-packs/{key}` | `read_subject_packs` |
| `/pilot/review-tasks` | `read_review_queue` |
| `/pilot/grading-results/{grading_result_id}/export` | `read_grading_exports` |
| `/pilot/grading-results/{grading_result_id}/reviewed-example` | `export_calibration` |
| `/pilot/answer-keys` | `write_answer_keys` |
| `/pilot/rubrics/{rubric_id}/draft` | `write_rubric_drafts` |

When these routes are eventually implemented, the route flow should be:

`HTTP request -> verified auth context -> tenant-scoped object load -> permission check -> service/workflow call -> audit event where needed -> response contract`

The route must not load by ID alone and return the object before proving the resource belongs to the request organization.

## Current Public Pilot Routes

The current Phase 4/5A HTTP routes stay public-safe and DB-free:

| Method | Path | Data boundary |
| --- | --- | --- |
| `POST` | `/pilot/fixtures/manifest/validate` | Caller-provided public-safe manifest |
| `POST` | `/pilot/evaluation/public-baseline` | Caller-provided public-safe manifest |

They do not load database records, private fixtures, provider prompts, real student data, or tenant-owned resources. They validate caller-provided public-safe payloads and return deterministic reports.

## Audit Expectations

Future DB-backed route work should define audit behavior before implementation:

- read-only metadata routes may not need audit rows unless they expose sensitive review or grading context
- mutation routes must create audit events through existing service-layer behavior
- export routes should record who exported, organization scope, resource id, and request id when the export includes tenant-owned grading or calibration data
- route handlers should pass request identity into services only through explicit contracts or workflow parameters

## Deferred Implementation

Phase 5B does not add:

- password login
- OAuth/OIDC/SAML
- API key issuance or verification
- JWT validation
- sessions or cookies
- production middleware
- DB-backed HTTP routes
- schema changes
- dependency changes

## Acceptance Criteria

Phase 5B is complete when:

- auth context, roles, permissions, and tenant-scoped resource checks are defined in code
- DB-backed route templates are mapped to required permissions
- tests prove cross-tenant and missing-permission access is rejected
- tests prove current pilot HTTP routes remain public-safe and not DB-backed
- docs clearly block DB-backed HTTP expansion until auth, tenancy, object-loading, and audit rules are implemented

## Next Phase

The next implementation phase is [Phase 5C production auth implementation planning](18-phase5c-production-auth-implementation-plan.md). It should choose one of two paths:

- implement real production auth context creation in a chosen framework, then add one read-only DB-backed route with tenant-scoped object loading; or
- stay framework-free and add only more public-safe, DB-free route examples.

Do not add review queue, grading-result lookup, answer-key mutation, rubric draft mutation, or calibration export routes over HTTP until production auth context is real.
