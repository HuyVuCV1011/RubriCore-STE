# Agent Instructions for `scripts/`

Scripts are development helpers for setup, seeding, fixtures, and smoke checks.

- Keep scripts safe for local development and explicit about side effects.
- Do not write real private data, credentials, or production records.
- Prefer synthetic seed data and idempotent behavior where practical.
- Avoid hiding schema changes or destructive database operations in helper scripts.
- Keep script dependencies aligned with project tooling in `pyproject.toml`.

Report any script side effects and verification commands.
