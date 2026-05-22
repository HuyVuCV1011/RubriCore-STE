# Rubric Framework Logic

This document describes the public rubric framework logic for RubriCore-STE. It focuses on rubric identity, versioning, criteria, score bands, descriptors, bindings, deterministic scoring, provenance, and review compatibility. Assessment classification belongs in [Assessment Taxonomy Logic](02-assessment-taxonomy.md). Durable database setup belongs in [Setup Database Logic](01-setupdb.md).

## Core Boundary

Rubrics define how evidence is evaluated. They should be readable by teachers, usable by deterministic scoring code, and traceable during grading, review, regrading, and audit.

Rubric logic is not an AI-provider layer. AI may later suggest draft criteria, descriptors, or feedback, but a rubric must work without prompts, providers, models, or generated text. Published rubric versions are grading context and should not be silently mutable.

## Implemented Entities

| Entity | Purpose |
| --- | --- |
| `Rubric` | Stable rubric identity with title, optional slug, lifecycle status, draft schema, and subject-agnostic metadata |
| `RubricVersion` | Immutable published snapshot with version number, schema payload, publisher, and source metadata |
| `RubricCriterion` | Ordered criterion or dimension with key, label, description, optional weight, and deterministic evaluation hints |
| `PerformanceLevel` | Ordered score band with key, label, description, and numeric score |
| `RubricDescriptor` | Narrative expectations for one criterion at one performance level |
| `RubricBinding` | Link from a published rubric version to an assessment, assessment item, or external evaluation context |

The framework keeps both:

- a JSON rubric snapshot on `RubricVersion.rubric_schema`, for durable audit and reconstruction
- normalized criteria, levels, descriptors, and bindings, for inspectable queries and deterministic scoring

## Rubric Lifecycle

The MVP lifecycle is:

`Draft Rubric -> Validate Draft Schema -> Publish RubricVersion -> Materialize Criteria / Levels / Descriptors -> Bind Version to Context -> Grade / Review / Audit`

Draft rubrics can change. Publishing creates the next numbered `RubricVersion`, records source metadata, and materializes the normalized rubric structure. After publication, scoring and review should reference the published version rather than the mutable draft.

Editing a published rubric should create a new draft and then a new published version. Past grading results should retain the original rubric version ID so review and audit can explain what was used at the time.

## Required Rubric Structure

A valid rubric schema must include:

- at least one criterion
- at least one performance level
- one descriptor for every criterion x performance-level pair
- unique criterion keys
- unique performance-level keys
- unique non-negative ordering positions within criteria and levels
- non-negative performance-level scores
- positive criterion weights when weights are provided
- non-empty descriptor narrative text

Criteria and levels are ordered by their `position` field. Subject-specific names may appear in labels or descriptions, but the core schema should not hardcode subject assumptions.

## Deterministic Scoring

The deterministic scoring helper accepts selected performance levels by criterion and computes:

- per-criterion score
- total score
- maximum possible score

For weighted criteria, the helper multiplies the selected performance-level score by the criterion weight. This is intentionally simple and explainable. It is suitable for deterministic checks, teacher review previews, and regression tests before any AI-assisted interpretation is introduced.

The deterministic scoring helper does not decide which level applies. It only computes scores from explicit selected levels. Selection may come from deterministic checks, teacher review, or a future validated suggestion layer.

## Binding Logic

`RubricBinding` attaches a published rubric version to one grading context without mutating the rubric itself.

Supported binding contexts are:

| Context type | Required field |
| --- | --- |
| `assessment` | `assessment_id` |
| `assessment_item` | `assessment_item_id` |
| `evaluation_context` | `external_context_key` |

Bindings carry lifecycle status, source, optional actor, timestamps, and metadata. This allows an assessment item to move to a new rubric version later while historical grading runs continue to point at the version that was actually used.

## Provenance and Audit Expectations

Rubric records should preserve enough context to answer:

- who created the rubric draft
- who published a rubric version
- which source or fixture produced a published version
- which criteria, levels, descriptors, and weights were available
- which rubric version was bound to an assessment context
- which rubric version a grading run or result used
- whether a teacher approved, adjusted, or overrode a result

Rubric metadata should stay public-safe in fixtures. Do not seed private rubrics, real student work, private prompts, provider credentials, confidential school data, or unpublished evaluation datasets.

## Teacher Review Compatibility

Teacher review should be able to inspect:

- criterion labels and descriptions
- ordered performance levels and scores
- descriptor narratives for selected or alternative levels
- deterministic score summaries
- grading-run and grading-result links to the rubric version used
- teacher overrides or finalization decisions

Review workflows may later add richer UI or policy rules. The current rubric framework supplies the stable scoring context those workflows need.

## Local Demo Seed

The development seed flow creates a synthetic demo rubric for the public Python score-summary fixture:

```sh
python scripts/seed_dev.py
```

The seed rubric is published through the same validation and versioning path as other rubrics. It is intentionally generic and public-safe.
