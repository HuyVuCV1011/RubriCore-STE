# Phase 6D Current-Schema Auth Readiness

This document defines the smallest production-auth readiness path that can use RubriCore-STE's current identity schema.

Phase 6D is a design slice only. It does not implement JWT verification, external identity lookup, user lookup code, membership tables, migrations, secrets, config loading, network calls, dependencies, or new routes.

## Decision

Use the existing organization-scoped `users` table for a narrow first production-auth readiness path.

This is intentionally more constrained than the long-term global-user plus external-identity plus membership model. The current schema can support a first verified-auth flow if the product accepts one important constraint:

`one User row represents one actor in one Organization`

Under that constraint, the current `users.organization_id`, `users.role`, and `users.status` fields can act as the first tenant access record.

## Current Schema Evidence

The current identity model already has:

| Table or field | Current use |
| --- | --- |
| `organizations.id` | Tenant boundary |
| `organizations.status` | Organization lifecycle |
| `users.id` | Internal actor id used by domain and audit records |
| `users.organization_id` | User's tenant scope |
| `users.email` | Organization-scoped user lookup candidate |
| `users.role` | Organization-scoped role |
| `users.status` | User access lifecycle |
| unique `(organization_id, email)` | Prevents duplicate email identities inside one tenant |

The current schema does not have external identity rows or organization membership rows. That absence is a limitation, but it is not a blocker for a deliberately narrow first auth readiness plan.

## Narrow Resolution Flow

A future provider implementation can use this current-schema flow:

`Authorization: Bearer <token> -> verify token -> resolve organization -> load active User by organization and email -> map User.role -> PilotAuthContext`

Required constraints:

- token issuer, audience, signature, algorithm, and lifetime must be verified before any claim is trusted
- token must provide a stable email claim or configured equivalent
- request must resolve to exactly one active organization
- user lookup must be scoped by organization
- `User.status` must be `active`
- organization status must be `active`
- `User.role` must map to a supported `PilotRole`
- route handlers still receive only `PilotAuthContext`

This flow should be limited to the existing first DB-backed route shape until a broader identity model is added.

## Role Mapping

The current user role values overlap with pilot roles:

| `users.role` | Pilot auth role |
| --- | --- |
| `admin` | `PilotRole.ADMIN` |
| `teacher` | `PilotRole.TEACHER` |
| `reviewer` | `PilotRole.REVIEWER` |
| `system` | `PilotRole.SYSTEM` |

The current `learner` role should not be granted pilot DB-backed route permissions unless a learner-facing route group is explicitly designed later.

Do not trust arbitrary token role claims as the source of tenant authorization in this current-schema path. Token role claims may be logged as provider hints or used as coarse prechecks only after issuer and audience are verified.

## What This Defers

This path defers, but does not reject, the long-term model from Phase 6C.

Deferred capabilities:

- global user identity independent of organization
- multiple organizations for one internal user row
- durable `(issuer, subject)` external identity mapping
- multiple identity providers for one user
- email-change-safe login
- organization membership lifecycle separate from user lifecycle
- membership-level `disabled_at`, `revoked_at`, invitation, or role history
- provider account linking

These are future product capabilities. They are not required to prove the first verified-auth boundary for the current read-only subject-pack route.

## Migration Triggers

Add identity migrations when the product needs one of these:

- one person can access multiple organizations without duplicate user rows
- login must be keyed by provider `issuer` and `subject` rather than email
- users can change email without breaking login identity
- one user can link multiple providers
- tenant access must be revoked independently from the user record
- membership invitations or role history become product requirements
- token organization claims need to be reconciled against explicit membership records

Until one of these triggers is accepted, migrations can be deferred.

## Failure Modes

The current-schema path should fail closed:

| Failure | API posture |
| --- | --- |
| Missing bearer token | `401 missing_auth_context` |
| Invalid token verification | `401 invalid_auth_context` |
| Missing email or organization scope claim | `401 invalid_auth_context` |
| Unknown organization | `401 invalid_auth_context` or `404`, chosen consistently before implementation |
| Archived organization | `403 forbidden` |
| Unknown user in organization | `401 invalid_auth_context` |
| Inactive or archived user | `403 forbidden` |
| Unsupported user role | `403 forbidden` |
| Authenticated role missing route permission | `403 forbidden` |

Error details must not reveal private tenant membership, real token payloads, or whether a cross-tenant user exists.

## Still Blocked

Phase 6D does not add:

- JWT verification code
- OIDC client configuration
- JWKS fetching or caching
- external identity tables
- organization membership tables
- schema changes or Alembic migrations
- secrets or credentials
- network calls
- new dependencies
- new DB-backed routes
- review queue routes
- grading-result export routes
- reviewed calibration export routes
- answer-key mutation routes
- rubric draft mutation routes
- provider calls or prompt execution
- private fixture loading

## Acceptance Criteria

Phase 6D is complete when:

- current schema auth resolution is documented
- narrow constraints are explicit
- `users.role` to `PilotRole` mapping is documented
- migration triggers are documented
- docs clearly state that migrations are deferred, not rejected
- docs clearly state that no real auth provider or token verification was added
