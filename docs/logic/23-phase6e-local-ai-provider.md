# Phase 6E Local AI Provider

Phase 6E adapts RubriCore-STE to a free local AI runtime while preserving the product rule that grading logic must remain provider-agnostic.

## Decision

Use Ollama as the first development local-AI provider.

Research notes from the official Ollama documentation:

- Ollama supports macOS Sonoma or newer on Apple silicon and x86 systems.
- The macOS install path is the Ollama app, with the CLI at `Ollama.app/Contents/Resources/ollama`.
- The local API is served at `http://localhost:11434/api`.
- `POST /api/chat` accepts a model name, chat messages, `format: "json"`, and `stream: false`, which matches RubriCore-STE's structured-output boundary.

Default local model:

- `llama3.2:1b`

This model is small enough for a local development machine and adequate for smoke-testing structured grading suggestions. Stronger local models can be swapped through configuration without changing grading orchestration.

## Product Boundary

The new provider lives in `app/ai/ollama.py` and implements the existing grading-provider protocol shape:

- `provider_name`
- `model_name`
- `evaluate(request_payload) -> dict`

Core grading orchestration still owns:

- deterministic-first grading
- request payload construction
- AI output validation
- confidence and review routing
- audit records

The Ollama adapter owns only:

- constructing a local chat request
- requesting JSON output
- parsing the model message content into a JSON object
- surfacing provider errors without mutating grading state
- repairing common local-model contract drift before core validation, such as rubric level names used as scores, confidence words used instead of numeric confidence, or malformed evidence references

## FastAPI Grading Route

Phase 6E also exposes the first authenticated grading execution route:

```text
POST /pilot/grading-runs
```

Request contract:

- `submission_id`
- optional `rubric_version_id`
- optional `answer_key_version_id`
- optional `selected_levels_by_criterion`
- `ai_allowed`, default `true`
- `ai_required`, default `false`
- confidence and review thresholds
- policy flags for answer-key requirement, auto-finalization, and mandatory review

Response contract:

- grading run id and status
- exported grading result, when one is produced
- review task id, when confidence or policy routes to review
- AI interaction summary, when local AI was invoked

Authorization:

- route policy: `/pilot/grading-runs`
- required permission: `run_grading`
- allowed by default for system, admin, and teacher roles
- not allowed for reviewer or read-only roles

Tenancy:

- submitted answer package, rubric version, and answer-key version are loaded through tenant-scoped helpers
- each loaded object must belong to the request organization
- missing explicit rubric or answer-key versions return `404`
- when no explicit rubric version is provided, existing grading-context resolution can still use active rubric bindings inside the service layer

Persistence:

- successful route execution commits the DB session when the session supports `commit`
- grading orchestration remains responsible for audit events, grading result creation, criterion results, review tasks, and AI interaction records
- orchestration errors roll back the session when the session supports `rollback`

## Demo UI and Seed Data

The development seed now creates a complete synthetic grading path:

- local development organization
- development admin user
- demo learner
- active demo assessment and item
- published demo rubric
- submitted demo answer package with code evidence

The FastAPI pilot app exposes:

```text
GET /pilot/demo/sample-grading-context
GET /pilot/ui
```

The demo context route is disabled in production and returns only the synthetic local ids needed to populate the pilot UI. The UI includes a `Load sample data` action, then submits to `POST /pilot/grading-runs`.

Live local smoke result:

- sample context loaded from the seeded database
- `POST /pilot/grading-runs` invoked Ollama `llama3.2:1b`
- AI interaction validated successfully
- grading run completed
- grading result auto-finalized through the existing confidence policy

## Configuration

Local configuration keys:

- `OLLAMA_BASE_URL`, default `http://localhost:11434`
- `OLLAMA_MODEL`, default `llama3.2:1b`
- `OLLAMA_TIMEOUT_SECONDS`, default `120`

## Setup

Install Ollama from the official macOS installer or script, then pull the default model:

```sh
/Applications/Ollama.app/Contents/Resources/ollama pull llama3.2:1b
```

If the `ollama` CLI symlink exists, the shorter form is:

```sh
ollama pull llama3.2:1b
```

Start the local API:

```sh
open -a Ollama --args hidden
```

Verify it:

```sh
curl http://localhost:11434/api/version
```

## Remaining Product Work

This phase does not add a teacher-facing UI, batch grading jobs, provider routing, retry budgets, model regression evaluation, or production deployment packaging. It creates the first real local-AI provider seam and a callable grading route so those pieces can build on a working adapter.
