# Audit Logging Logic

This document describes the public Phase 1 audit logging boundary for RubriCore-STE. Audit logging records important lifecycle, grading, review, and configuration actions as append-only `AuditEvent` records.

## Implemented Event Shape

`AuditEvent` records include:

- organization, assessment, submission, and grading run context when relevant
- actor user or system source
- action name
- entity type and entity ID
- request ID or job ID when available
- previous state summary
- new state summary
- reason or source when available
- creation timestamp from the common timestamp mixin

Audit records are queryable by organization, actor, entity, assessment, submission, grading run, and creation time.

## Covered Phase 1 Actions

Current Phase 1 services emit audit events for:

- rubric draft creation
- rubric version publication
- rubric binding creation
- submission creation, submission, evidence mutation, revision, withdrawal, archive, and superseding
- regrade request creation
- grading run creation, start, completion, and failure
- deterministic grading summary
- AI interaction validation success, validation failure, and provider failure
- review task creation
- auto-finalization
- teacher review completion
- teacher override application
- return for regrade and delegated regrade requests
- grading result superseding

Answer-key creation and publication have durable models and are referenced by grading runs and results, but Phase 1 does not yet expose a dedicated answer-key lifecycle service. When that service is added, it should emit the same style of append-only audit events for answer-key draft creation and version publication.

## Traceability

The audit trail should help reconstruct:

- which rubric version was created, published, bound, and later used
- which answer key version was used when answer-key grading applies
- which submitted evidence package was graded
- which deterministic selections, scores, warnings, and answer-key findings were produced
- whether AI contributed, which provider and model were used, and whether validation passed
- why a result was auto-finalized, routed to review, returned for regrade, or changed by a teacher
- who performed a human action and why

Detailed scores, criterion rows, teacher reviews, overrides, and AI interactions remain in their primary records. Audit events summarize material transitions and link back to those records instead of becoming the only source of domain data.

## Phase 1 Limits

Audit logging is not a workflow engine, reporting API, retention policy, or compliance export. It is the durable append-only event layer that future reporting, admin UI, and compliance workflows can query.
