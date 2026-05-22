# Agent Instructions

RubriCore-STE is an early-stage Python backend for rubric-driven assessment, deterministic grading, teacher review, reusable grading knowledge, and auditable decisions.

## Working Rules

- Inspect related models, migrations, tests, and docs before editing.
- Prefer small, reviewable changes that fit the existing docs-first and schema-first workflow.
- Preserve grading, review, versioning, and audit semantics unless explicitly asked to change them.
- Do not change database schema or Alembic migrations without clear approval.
- Prefer deterministic checks before adding AI-related grading logic.
- Keep AI/provider-specific details behind stable internal boundaries.
- Keep fixtures synthetic and safe. Do not add real student data, private rubrics, prompts, credentials, or private knowledge sources.
- Avoid unrelated refactors, formatting churn, and business-logic changes.

## Tooling

- Use `uv sync --dev` to create/update the local environment.
- Use `uv run ruff format .`, `uv run ruff check .`, `uv run pyright`, and `uv run pytest`.
- Use `pre-commit run --all-files` before handing off broad changes.
- Use Repomix only for repository packaging; do not include `.env`, private docs, local artifacts, caches, or virtual environments.

## Handoff Report

After each task, report:

- files changed
- whether business logic changed
- whether schema or migrations changed
- verification commands run
- remaining risks or ambiguities
