# Confidence Policy Logic

This document describes the public Phase 1 confidence policy logic for RubriCore-STE. It focuses on how grading orchestration interprets confidence, validates confidence-related signals, and routes candidate results to finalization or teacher review.

Grading execution is described in [Grading Orchestration Logic](05-grading-orchestration.md). Submitted answer package immutability is described in [Answer Lifecycle](04-answer-lifecycle.md). Rubric scoring boundaries are described in [Rubric Framework Logic](03-rubric-framework.md).

## Core Boundary

Confidence is an auditable policy summary of whether a candidate grading result is valid, complete, evidence-supported, and eligible for the requested routing action.

It is not:

- a replacement for deterministic validation
- a model-only trust score
- a teacher override
- a reason to hide ambiguity
- a reason to finalize incomplete rubric coverage

The final routing decision is separate from the raw confidence value. High confidence can still route to review when a policy gate applies.

## Implemented Service Shape

The current backend slice implements confidence policy inside `app.db.services.grading_orchestration`.

The implemented policy uses:

- `GradingPolicy.confidence_threshold`
- `GradingPolicy.review_threshold`
- `GradingPolicy.auto_finalize_allowed`
- `GradingPolicy.mandatory_review`
- deterministic scoring confidence
- validated AI aggregate confidence
- rubric coverage checks
- AI validation status
- deterministic/AI disagreement checks

The default Phase 1 thresholds are:

| Setting | Default |
| --- | --- |
| `confidence_threshold` | `0.85` |
| `review_threshold` | `0.70` |

## Confidence Bands

| Band | Rule | Meaning |
| --- | --- | --- |
| `high` | confidence is at or above `confidence_threshold` | eligible for auto-finalization only if all gates pass |
| `medium` | confidence is at or above `review_threshold` but below `confidence_threshold` | plausible but review-routed by default |
| `low` | confidence is above `0` but below `review_threshold` | uncertain and review-routed |
| `blocked` | confidence is missing, zero, or blocked by validation | no safe automated finalization |

The implementation uses configured policy thresholds when assigning bands. Thresholds should not be treated as universal constants.

## Allowed Confidence Inputs

The policy can use:

- deterministic score confidence
- validated AI aggregate confidence
- valid AI criterion confidence
- rubric criterion coverage
- structured AI validation status
- deterministic/AI score agreement
- mandatory review policy
- auto-finalization policy

The policy should not use hidden provider heuristics, unrelated learner data, prompt length, latency, or unvalidated AI prose as confidence signals.

## Routing Rules

A result may auto-finalize only when:

- the submitted package and grading context are valid
- deterministic checks completed
- AI output is valid when AI is required or used for scoring
- all required rubric criteria are covered by deterministic or valid AI results
- scores are within rubric bounds
- confidence is in the `high` band
- no deterministic/AI disagreement exists
- mandatory review is not enabled
- auto-finalization is allowed

The service creates a `ReviewTask` when:

- confidence is below the auto-finalization threshold
- confidence is missing
- rubric coverage is incomplete
- AI output fails validation
- AI is required but no valid AI payload exists
- deterministic and AI scoring disagree
- mandatory review is enabled
- auto-finalization is disabled

Review tasks preserve confidence band, escalation reason, policy payload, grading run ID, grading result ID, and submission context.

## Persistence

`GradingResult.explanation_payload` stores:

- confidence summary
- source confidence values
- confidence band
- policy thresholds
- AI validation summary
- rubric coverage summary
- disagreement flags
- routing decision and reason codes

`ReviewTask.policy_payload` stores reviewer-facing routing context:

- decision
- confidence and band
- reason codes
- policy version
- thresholds
- review priority
- coverage summary
- AI validation summary
- disagreement flags

This keeps confidence explainable without requiring reviewers or auditors to reconstruct decisions from raw provider output.

## Current Verification

Run confidence-related grading tests:

```sh
.venv/bin/pytest tests/test_grading_orchestration.py
```

Run the full suite:

```sh
.venv/bin/pytest
```

The current tests cover high-confidence auto-finalization, low-confidence review routing, AI-only full-coverage finalization, mandatory review overriding high confidence, incomplete rubric coverage overriding high confidence, invalid AI output routing, and deterministic/AI disagreement routing.

## Phase 1 Limits

This slice intentionally defers:

- calibrated statistical confidence models
- adaptive threshold learning
- multi-model voting
- provider-specific confidence normalization
- reviewer sampling programs
- advanced score-boundary policies
- subject-specific confidence formulas

Phase 1 favors a small, explicit gate-based confidence policy over hidden scoring formulas.
