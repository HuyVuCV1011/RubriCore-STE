# Phase 2 Readiness

This document marks the Phase 2 backend MVP readiness boundary for RubriCore-STE.

## Readiness Status

| Area | Status |
| --- | --- |
| Phase 2 backend MVP | Complete |
| Public API/UI | Deferred |
| Rich import, vector retrieval, and provider integrations | Deferred |
| Phase 3 evaluation/calibration foundation | Ready to begin |

Phase 2 is complete as a backend MVP, not as a production product. The repository now has the knowledge-library backend slice, pilot service helpers, typed pilot contracts, a reusable pilot workflow facade, documentation, and tests needed to support later API/UI work without rebuilding the backend foundation.

## Completed Backend Foundation

Phase 2 backend MVP includes:

- knowledge source registration and versioned source identity
- Markdown and plain-text conversion into normalized Markdown artifacts
- deterministic chunk creation and scoped non-vector retrieval
- citation-backed rubric suggestion drafts
- teacher acceptance, edited acceptance, rejection, and superseding of suggestions
- draft rubric updates without mutating published rubric versions
- subject-pack, answer-key, review-queue, rubric-authoring, export, and calibration pilot services
- Pydantic pilot request/response contracts
- reusable pilot workflow facade for future API, job, CLI, or UI adapters
- smoke workflow coverage for the pilot backend flow

## Deferred Productization

The following remain outside the Phase 2 backend MVP:

- public API route implementation
- teacher-facing UI
- production authentication and authorization
- production upload sessions and object storage
- rich parsing for PDF, DOCX, spreadsheets, images, archives, and notebooks
- embeddings and vector retrieval
- external AI provider calls for suggestion generation
- provider routing, fallback policy, and deployment packaging

## Phase 3 Starting Checklist

Phase 3 should begin with evaluation and calibration infrastructure:

- Define an evaluation dataset format for synthetic grading cases.
- Add grading-result comparison metrics for score, criterion, feedback, and routing behavior.
- Create calibration examples from finalized reviewed results.
- Add regression tests for model/prompt behavior at the provider boundary.

The first Phase 3 slice should stay backend-first and public-safe. It should use synthetic fixtures and avoid real student data, private prompts, private rubrics, or provider credentials.

