# Agent Instructions for `app/db/`

This directory owns SQLAlchemy models, database setup, seed helpers, and database-oriented services.

- Treat schema, migrations, and audit fields as durable product contracts.
- Do not change models, relationships, enums, indexes, or Alembic migrations without clear approval.
- If a schema change is approved, update models, migrations, tests, and docs together.
- Preserve immutable published rubric/answer-key context and traceable grading/audit history.
- Keep seed data synthetic and public-safe.
- Prefer clear SQLAlchemy relationships and explicit metadata over clever abstractions.

Report clearly whether schema or migration files changed.
