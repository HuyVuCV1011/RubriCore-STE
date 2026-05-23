# Review Policy Logic

This document describes the public Phase 1 review-policy logic for RubriCore-STE. Review policy starts after grading orchestration has produced a candidate `GradingResult` that cannot safely auto-finalize.

Grading execution is described in [Grading Orchestration Logic](05-grading-orchestration.md). Confidence routing is described in [Confidence Policy Logic](06-confidence-policy.md). Submitted answer immutability is described in [Answer Lifecycle](04-answer-lifecycle.md).

## Implemented Service Shape

The current backend slice implements teacher review decisions in `app.db.services.review_policy`.

The implemented review workflow uses existing Phase 1 records:

- `ReviewTask`
- `TeacherReview`
- `TeacherOverride`
- `GradingResult`
- `CriterionResult`
- `GradingRun`
- `AuditEvent`

No extra review-policy schema is required for this slice.

## Review Task Creation

Grading orchestration creates a `ReviewTask` when confidence, validation, coverage, disagreement, or policy gates require human review.

The routing layer stores:

- organization, assessment, item, submission, run, and result context
- confidence band
- primary escalation reason
- all policy reason codes in `policy_payload`
- thresholds and policy version
- reviewer-facing summaries for coverage, AI validation, and disagreement

If an open or assigned task already exists for the same grading result, orchestration reuses that task and refreshes its policy payload instead of creating a duplicate.

## Teacher Actions

The review-policy service supports:

- approve result
- finalize result
- adjust total score
- edit feedback
- override criterion result
- return for regrade

Every teacher decision requires:

- reviewer actor
- reason
- review task
- grading result
- submission context

Teacher actions are allowed only for open or assigned review tasks whose grading result is still `needs_review`.

## Overrides

Score, feedback, and criterion changes create `TeacherOverride` records.

Override records preserve:

- actor through `overridden_by_user_id`
- reason
- affected grading result
- previous payload
- new payload
- related teacher review

Criterion overrides add a teacher-sourced `CriterionResult` instead of mutating the original deterministic or AI criterion result.

## Finalization

Approval or finalization sets:

- `GradingResult.status = 'finalized'`
- `GradingResult.result_type = 'reviewed'`
- `ReviewTask.status = 'completed'`

Adjustments and overrides set:

- `GradingResult.status = 'finalized'`
- `GradingResult.result_type = 'overridden'`
- `ReviewTask.status = 'completed'`

The original confidence and routing facts remain in `GradingResult.explanation_payload`. Human review history and finalization source are appended to the explanation payload.

## Return For Regrade

Returning a review for regrade:

- creates `TeacherReview(decision='return_for_regrade')`
- completes the review task
- keeps the current result in `needs_review`
- creates a queued `GradingRun` against the same immutable submitted evidence
- stores review task, teacher review, and previous result context in the regrade run payload

Regrade does not mutate submitted evidence.

## Audit Events

Review policy emits audit events for:

- teacher review completion
- teacher override application
- return for regrade
- the delegated regrade request

Audit payloads include previous and new state summaries, review task id, grading result id, actor, reason, and request id when provided.

## Phase 1 Limits

This slice does not implement reviewer assignment rules, public UI/API endpoints, dispute case records, score-boundary configuration, reviewer sampling programs, or AI retry budgeting.

Those concerns can build on the review service without changing the current review decision contract.
