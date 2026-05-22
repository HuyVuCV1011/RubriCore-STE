# Agent Instructions for `app/`

This directory contains the Python backend package. Keep edits modular and aligned with the subject-agnostic assessment core.

- Inspect nearby modules before editing imports, public APIs, or shared helpers.
- Preserve grading lifecycle, teacher-review, audit, and versioning semantics.
- Do not couple core logic directly to a specific AI provider, model, database implementation detail, or future web framework.
- Prefer explicit validation and deterministic behavior before AI-assisted logic.
- Keep comments concise and useful.
- Avoid adding framework entrypoints here unless the task explicitly asks for an API layer.

Report whether any application behavior changed in the handoff.
