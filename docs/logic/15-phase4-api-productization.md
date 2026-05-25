# Phase 4 API Productization

This document starts Phase 4 as a small backend API productization slice. It defines the route boundary and adapter foundation for exposing existing service-layer behavior without changing grading semantics, adding UI, adding provider integrations, or weakening public/private data boundaries.

Phase 4 begins with a framework-free adapter layer in `app.pilot.api_adapters` and a minimal stdlib HTTP boundary in `app.pilot.http_api`. The current shape is a pilot route dispatcher and optional local `http.server` handler, not a production web stack.

## Implemented Pilot Boundary

The Phase 4 HTTP boundary is intentionally small and local-first:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/pilot/health` | Local smoke health check |
| `GET` | `/pilot/routes` | Local route discovery for the pilot boundary |
| `POST` | `/pilot/fixtures/manifest/validate` | Validate a caller-provided public-safe fixture manifest payload |
| `POST` | `/pilot/evaluation/public-baseline` | Produce a baseline evaluation report from a caller-provided public-safe manifest payload |

Run it locally with:

```sh
.venv/bin/python -m app.pilot.http_api --host 127.0.0.1 --port 8080
```

Run the local smoke script with:

```sh
.venv/bin/python scripts/smoke_phase4_http_api.py
```

The smoke script starts an ephemeral local server when local socket binding is available. In restricted sandboxes that prohibit binding local sockets, it falls back to the same dispatcher used by the HTTP handler. In both modes it calls the health path, validates a synthetic fixture manifest, and produces the public evaluation baseline report from `tests/fixtures/public/python_score_summary/evaluation_cases/manifest.json`.

## Scope

The first Phase 4 slice may expose or prepare route adapters for backend workflows that are already deterministic, contract-backed, and public-safe:

| Workflow | Initial adapter posture | Existing backend source |
| --- | --- | --- |
| Fixture manifest validation | Safe to expose first | `FixtureManifestRequest`, `validate_fixture_manifest_workflow` |
| Public evaluation fixture baseline | Safe to expose first when caller provides a public-safe manifest payload | `validate_fixture_manifest`, `evaluation_dataset_report` |
| Subject-pack summary normalization | Safe to expose first as a read/summary shape | `SubjectPackSummaryResponse` |
| Grading-result export shape | Safe to expose first for already-resolved result objects | `export_grading_result_workflow` |
| Reviewed-result calibration export shape | Safe to expose first for already-resolved reviewed/finalized objects | `reviewed_example_payload_workflow` |

The first slice intentionally avoids persistence or authorization decisions in route-like code. Object loading, access checks, pagination, and production auth remain future API work. The HTTP layer only handles JSON transport concerns, route lookup, contract validation errors, and delegation to existing adapters.

## Non-Goals

Phase 4 does not yet add:

- teacher-facing UI
- production authentication or authorization
- provider calls or prompt execution
- provider routing, fallback policy, or credentials
- vector retrieval
- rich file upload/import for PDF, DOCX, spreadsheets, images, archives, notebooks, or object storage
- private fixture loading
- schema changes or Alembic migrations
- new runtime dependencies

The selected HTTP boundary is Python stdlib `http.server` plus a testable dispatcher. Do not add a web framework until the route contract, auth boundary, deployment shape, OpenAPI needs, and data-access rules are clear enough to justify it.

## API Boundary Principles

Future HTTP routes should follow the same boundary as the Phase 2 pilot plan:

`HTTP route -> Pydantic contract -> adapter/workflow -> service function -> response contract`

Route handlers should stay thin. They may parse path/query/body inputs, construct Pydantic contracts, call an adapter or workflow, and map expected errors to HTTP responses. They should not own grading, review, rubric versioning, answer-key publishing, audit behavior, evaluation metrics, provider prompts, or fixture privacy rules.

Business rules remain in services and existing workflow helpers. API adapters are allowed to define route-shaped entry points, but they should mostly validate input and delegate.

## Public/Private Data Handling

Public API smoke tests and docs must use only synthetic public-safe fixtures under `tests/fixtures/public/`.

Public-safe manifests must:

- declare `privacy="public_safe"`
- use relative fixture paths that stay inside the fixture root
- avoid private prompts, private rubrics, credentials, real learner markers, school names, and other sensitive markers
- remain synthetic enough for GitHub review and CI

Private or real-world datasets must stay only in ignored local paths such as `tests/fixtures/private/evaluation/` or `private-docs/evaluation/`. Tracked docs and tests may describe those local boundaries, but must not include private file contents, private prompts, private rubrics, real student work, credentials, or local secret paths.

## Service-Only For Now

The following workflows remain service-only or future-only until their data, auth, and product boundaries are designed:

| Workflow | Reason to defer |
| --- | --- |
| Provider calls and prompt execution | Requires provider credentials, prompt safety, trace policy, and regression harnesses |
| Vector retrieval | Requires retrieval policy, index lifecycle, data partitioning, and citation guarantees |
| Rich file upload/import | Requires upload sessions, storage policy, parsing safety, and artifact lifecycle rules |
| Private fixture loading | Must remain local/ignored and requires explicit operator controls |
| Production auth and authorization | Needs identity, tenancy, role, and audit rules before public routes |
| Teacher-facing UI | Should consume a stable API after backend boundaries are clear |

## Recommended Future Route Groups

Use an unstable `/pilot` prefix until the API is product-stable.

| Route group | Candidate routes | Phase 4 readiness |
| --- | --- | --- |
| Fixture validation | `POST /pilot/fixtures/manifest/validate` | Implemented in stdlib pilot HTTP boundary |
| Evaluation reports | `POST /pilot/evaluation/public-baseline` | Implemented in stdlib pilot HTTP boundary for provided public-safe manifests |
| Subject packs | `GET /pilot/subject-packs/{key}`, `POST /pilot/subject-packs/summary` | Summary adapter ready; DB-backed resolution needs auth/object-loading policy |
| Grading exports | `GET /pilot/grading-results/{id}/export` | Response adapter ready; DB-backed route needs auth/object-loading policy |
| Calibration exports | `GET /pilot/grading-results/{id}/reviewed-example` | Response adapter ready; DB-backed route needs auth/object-loading policy |
| Review queues | `GET /pilot/review-tasks` | Service/workflow exists; production API needs auth, tenancy, pagination, and reviewer permissions |
| Answer keys and rubric drafts | `POST/PATCH /pilot/answer-keys`, `PATCH /pilot/rubrics/{id}/draft` | Workflow exists; API should wait for auth, draft ownership, and UI workflow requirements |

## Acceptance Criteria

The Phase 4 first slice is acceptable when:

- route-like adapters exist without adding a new dependency
- the first two pilot HTTP routes exist without adding a web framework
- the pilot boundary has a local smoke script that starts a server and exercises the implemented routes
- adapters use Pydantic contracts where the current payload shape supports them
- adapters delegate to existing workflow or service helpers instead of reimplementing business logic
- public fixture validation still rejects private or sensitive markers
- a public evaluation baseline can be produced through the adapter from the synthetic public manifest
- no private files are required for tests or smoke checks
- Phase 1, Phase 2, and Phase 3 tests still pass
- README links this document and accurately says UI, provider integrations, rich import, vector retrieval, and production auth remain deferred

## Next Slice

The recommended next product step after Phase 4 is to decide whether the stdlib pilot HTTP boundary remains sufficient for local smoke use, or whether the project should adopt a production framework such as FastAPI once auth, tenancy, deployment, and OpenAPI requirements are ready. Do not expand to DB-backed route groups until object-loading, tenancy, and permission checks are designed.
