# Phase 3 Evaluation Foundation

This document describes the Phase 3 backend evaluation and calibration foundation for RubriCore-STE. It keeps the slice public-safe and schema-free: evaluation datasets, public/private data rules, deterministic metric helpers, reviewed-result calibration export, and a local public-fixture runner for comparing grading-like outputs.

Phase 3 evaluation work is for measuring grading behavior over time. It is not a public API, UI, provider integration, or production benchmark runner.

## Evaluation Dataset Purpose

Evaluation datasets provide repeatable cases for checking whether grading behavior stays aligned with expected outcomes as rubrics, prompts, deterministic checks, review routing, and provider boundaries evolve.

Use evaluation datasets to compare:

- total score delta
- criterion-level score agreement
- final versus review routing agreement
- future feedback, citation, confidence, and provider-boundary behavior

Evaluation datasets should describe expected behavior, not become hidden grading authority. Published rubrics, answer keys, deterministic checks, teacher review decisions, and audit records remain the source of truth for normal grading workflows.

## Public Fixture Boundary

Public fixtures belong under `tests/fixtures/public/` and must be safe to commit to GitHub.

Public-safe evaluation fixtures may include:

- fake learner responses
- fake rubrics and scoring guides
- fake expected outcomes
- fake metadata such as `fake_learner_alpha`
- synthetic assessment materials
- relative references to other public fixture files
- public-safe manifests with `privacy="public_safe"`

Public fixtures must not include:

- real student work
- private prompts
- private rubrics
- private school, teacher, learner, or organization names
- learner identifiers from real systems
- credentials, API keys, tokens, or provider secrets
- private knowledge-library sources
- unpublished private evaluation datasets

The current public evaluation fixture is `tests/fixtures/public/python_score_summary/evaluation_cases/manifest.json`. It references only synthetic public files inside the existing Python score-summary fixture set.

## Private Dataset Boundary

Private or sensitive evaluation data belongs only in local ignored paths, such as:

- `tests/fixtures/private/evaluation/`
- `private-docs/evaluation/`
- another ignored local artifact directory documented outside tracked source files

Private datasets should stay out of GitHub-tracked files. Tracked docs may describe the expected local location and manifest shape, but should not list private school names, student names, prompts, rubrics, source excerpts, or local file contents.

Private evaluation datasets should have a public-safe fallback whenever automated tests, examples, or CI workflows need a dataset. Clean-clone verification must not require private fixtures.

## Synthetic Versus Private Data

Public-safe synthetic examples are invented for testing and documentation. They may look realistic enough to exercise the backend, but they are not copied from real learner work, real classrooms, private teacher materials, or confidential school systems.

Private school or student data includes any real or sensitive material, even after light editing. That includes real learner responses, teacher prompts, grading notes, rubrics, rosters, organization names, IDs, source documents, or evaluation results derived from private classroom activity.

When in doubt, treat the data as private and keep it in ignored local paths.

## Source References

Evaluation artifacts should reference source files by relative paths that stay inside the fixture root. They should not expose private content in tracked manifests.

Public-safe manifests may reference public files like:

```json
{
  "path": "submission_evidence/student_001_correct.py",
  "purpose": "submission_evidence",
  "description": "Fake learner response used for an expected final outcome."
}
```

Do not use absolute paths, parent-directory escapes, local usernames, object-storage URLs, signed URLs, or private source excerpts in public manifests.

For private/local evaluation datasets, tracked code should accept relative references, but the referenced files and their manifest should remain in ignored local locations.

## Validation Expectations

Public evaluation manifests must:

- declare `privacy="public_safe"`
- use only relative paths that stay inside the fixture root
- avoid sensitive markers such as private prompts, private rubrics, credentials, real learner markers, or private school markers
- use public-safe fake metadata
- remain synthetic enough for public CI and GitHub review

The Phase 3 helper layer intentionally avoids schema and migration changes. Metric helpers operate on structured payloads or grading-result-like objects so future API, job, or provider adapters can reuse them without moving business logic into routes.

## Local Evaluation Reports

Evaluation reports compare manifest `expected_outcome` values against actual outcome payloads keyed by `case_id`.

The backend report includes:

- fixture set and privacy metadata
- case count and evaluated count
- pass/fail count
- missing actual outcomes
- per-case score, criterion, and routing metrics

The public smoke runner is:

```sh
.venv/bin/python scripts/run_public_evaluation_fixture.py --baseline
```

`--baseline` compares each public synthetic case against itself and verifies the fixture/report path. For real actual outcomes, pass a JSON object keyed by `case_id` with `--actual-outcomes`. Private actual-outcome files must remain in ignored local paths.

## Reviewed-Result Calibration Export

Finalized `reviewed` and `overridden` grading results can be converted into public-safe evaluation comparison payloads. The export shape mirrors synthetic evaluation cases:

- `expected_outcome.total_score`
- `expected_outcome.max_score`
- `expected_outcome.routing`
- `expected_outcome.criteria`
- public-safe metadata about the calibration source

Reviewed-result calibration exports use `routing="review"` because they represent examples that passed through human review or override before becoming trusted expected outcomes.

The export helper does not read private files, call providers, create database rows, or expose feedback text, prompt text, rubric text, learner identifiers, or source excerpts. Private/local callers must still keep the resulting datasets in ignored local paths unless the exported case is synthetic and public-safe.

## Deferred Work

Later work may add:

- provider-boundary regression harnesses
- confidence and feedback quality metrics
- richer private/local dataset runners
- CI integration for the public baseline runner

Those additions should preserve the public/private boundary defined here.
