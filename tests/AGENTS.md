# Agent Instructions for `tests/`

Tests should protect taxonomy boundaries, artifact provenance, grading semantics, and future review/audit behavior.

- Keep public fixtures synthetic. Never add real learner work, private prompts, private rubrics, credentials, or private school data.
- Prefer focused tests that describe expected behavior and edge cases.
- Do not weaken tests to make implementation pass.
- When adding business behavior, add or update tests near the changed surface.
- Keep fixture paths stable unless the task explicitly includes fixture reorganization.

Report the exact test commands run and any skipped coverage.
