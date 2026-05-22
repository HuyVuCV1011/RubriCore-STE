# Answer Lifecycle

Phase 1 treats a learner answer as an immutable answer package once submitted.

## Implemented States

Submission package states:

- `draft`: editable package before official submission
- `submitted`: immutable package available for grading
- `superseded`: historical package replaced by a newer package
- `withdrawn`: cancelled package that should not be graded
- `archived`: inactive preserved package

Compatibility statuses from earlier schema work still exist for now:

- `processing`
- `graded`
- `returned`

New lifecycle code should not treat those compatibility statuses as authoritative. Processing belongs to jobs and grading runs. Finalization belongs to grading results. Review workflow belongs to review tasks and teacher decisions.

## Core Rules

- Submitted evidence is immutable grading input.
- Learner revisions create a new answer package instead of mutating the submitted package.
- Regrades create new grading runs against unchanged submitted evidence.
- New answer packages explicitly supersede older packages.
- New grading results explicitly supersede older grading results.
- Important lifecycle actions create audit events.
- Deterministic intake validation runs before AI-assisted processing.

## Verification

Run the answer lifecycle tests:

```bash
.venv/bin/pytest tests/test_answer_lifecycle.py
```

Run the broader current test suite:

```bash
.venv/bin/pytest
```

## Phase 1 Limits

Phase 1 does not add a separate `Attempt` table. The `submissions` table represents the answer package boundary and includes explicit superseding metadata. A future attempt or learner-assessment-instance aggregate can be added without changing the core immutability rule.
