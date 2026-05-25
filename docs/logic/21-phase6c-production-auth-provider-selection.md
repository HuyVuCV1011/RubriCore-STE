# Phase 6C Production Auth Provider Selection

This document chooses the first production auth provider shape for RubriCore-STE.

Phase 6C is a design slice only. It does not implement JWT verification, session handling, API keys, user lookup, membership lookup, secrets, config loading, network calls, dependencies, schema changes, or new routes.

## Decision

Use OIDC/JWT bearer tokens as the first production auth provider style.

Rationale:

- it fits hosted identity providers and non-browser API clients
- it keeps production auth outside route handlers through the Phase 6B `AuthProvider` interface
- it gives clear validation inputs: issuer, audience, signing keys, expiry, algorithms, and claims
- it can support a later first-party UI without forcing session cookies into the service layer

Session cookies and API keys remain possible future adapters, but they should be separate implementations of the same provider boundary.

## Future Adapter Shape

A future provider should implement:

`AuthProvider.verify_request(headers) -> PilotAuthContext`

Expected future request flow:

`Authorization: Bearer <token> -> OIDC/JWT verification -> identity lookup -> membership lookup -> organization scope resolution -> PilotAuthContext`

The route layer should still receive only `PilotAuthContext`. Route handlers should not read JWT claims, provider subjects, scopes, or raw token payloads.

## Required Configuration Inputs

The eventual OIDC/JWT provider should require explicit configuration for:

| Input | Purpose |
| --- | --- |
| issuer | Reject tokens from unexpected identity providers |
| audience | Reject tokens minted for other applications |
| JWKS URL | Fetch public signing keys for token verification |
| allowed algorithms | Prevent accepting unexpected signing algorithms |
| clock skew seconds | Bound tolerance for token time validation |
| organization claim name | Locate requested organization scope if claims carry one |
| provider subject claim | Locate stable provider user identity |

Configuration should come from deployment environment or secret management, not tracked fixtures, README examples with real values, or code constants with private data.

## Claim Mapping

Future claim mapping should be explicit and conservative:

| Provider claim | Internal use |
| --- | --- |
| `sub` or configured subject claim | Resolve the provider identity to an internal user |
| `iss` | Validate issuer and optionally record provider issuer in request metadata |
| `aud` | Validate intended API audience |
| `exp`, `nbf`, `iat` | Validate token lifetime |
| configured organization claim | Select or constrain organization scope only after membership lookup |
| email claim | Optional display or matching hint, not an authorization source by itself |

Roles should not be trusted from arbitrary token claims unless the issuer, audience, claim contract, and membership model explicitly support that. The safer production default is to map token identity to an internal user and load active organization membership from the database.

## Organization And Membership Resolution

Prefer DB-backed membership lookup for production authorization.

Recommended flow:

1. Verify token authenticity, issuer, audience, algorithm, and lifetime.
2. Resolve provider subject and issuer to an internal user identity.
3. Reject disabled or unknown users.
4. Resolve requested organization scope from a configured claim or explicit request context.
5. Load active membership for the internal user and organization.
6. Reject disabled, missing, or ambiguous membership.
7. Map internal membership roles to `PilotRole`.
8. Return `PilotAuthContext`.

The token may constrain organization scope, but it should not by itself grant tenant access to DB-backed resources.

## Failure Modes

The eventual provider should distinguish these failure classes without leaking private data:

| Failure | API posture |
| --- | --- |
| Missing bearer token | `401 missing_auth_context` |
| Malformed authorization header | `401 invalid_auth_context` |
| Invalid signature or unknown key | `401 invalid_auth_context` |
| Invalid issuer | `401 invalid_auth_context` |
| Invalid audience | `401 invalid_auth_context` |
| Expired or not-yet-valid token | `401 invalid_auth_context` |
| Missing required claims | `401 invalid_auth_context` |
| Unknown or disabled user | `401 invalid_auth_context` |
| Missing, disabled, or ambiguous membership | `403 forbidden` or `401 invalid_auth_context`, chosen consistently before implementation |
| Authenticated but unauthorized role | `403 forbidden` |

Operational logs may record provider-safe diagnostics, but tracked tests and public docs must not contain secrets, real tokens, private claims, or production tenant data.

## Still Blocked

Do not implement or expose these as part of Phase 6C:

- JWT verification code
- JWKS fetching or caching
- OAuth/OIDC client configuration
- session cookies
- API-key issuance or verification
- secrets or credentials
- user or membership tables
- schema changes or Alembic migrations
- review queue routes
- grading-result export routes
- reviewed calibration export routes
- answer-key mutation routes
- rubric draft mutation routes
- provider calls or prompt execution
- private fixture loading

## Acceptance Criteria

Phase 6C is complete when:

- OIDC/JWT bearer tokens are selected as the first production provider style
- required future config inputs are documented
- claim mapping is documented
- DB-backed organization membership lookup is the preferred authorization source
- failure modes are documented
- docs clearly state that no real auth provider or token verification was added
