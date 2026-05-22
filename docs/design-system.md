# RubriCore-STE Design System

RubriCore-STE is a subject-agnostic assessment platform core for evaluating student work across multiple disciplines. This document describes the public product and system design principles behind the platform. It is not a UI style guide and does not include private prompts, student data, credentials, or implementation code.

## Project Vision

RubriCore-STE is designed to support trustworthy assessment workflows across subjects such as Data, Programming, Math, Physics, Art, and future disciplines.

The platform is built around rubrics, evidence, assessment types, review workflows, and auditability. Subjects are treated as configuration packs rather than hard-coded product logic.

The long-term goal is to provide a reusable assessment core that is:

- subject-agnostic
- rubric-driven
- explainable
- teacher-trustable
- extensible across disciplines
- compatible with multiple AI providers and future self-hosted models

## Subject-Agnostic Architecture

RubriCore-STE does not organize its core model around fixed roles, professions, or subjects. The platform is centered on reusable assessment primitives:

- **Assessment type**: the nature of the task being evaluated.
- **Evidence type**: the form of student work submitted.
- **Output type**: the expected shape of the response or produced work.
- **Rubric type**: the scoring structure used for evaluation.
- **Subject pack**: portable configuration for a discipline or curriculum area.

Subject-specific behavior belongs in subject packs. Core grading, review, versioning, and audit workflows remain generic.

## Assessment Taxonomy

Assessment taxonomy is for classification and compatibility. It describes what kind of task is being evaluated, what evidence can be accepted, what output shape is expected, and which rubric styles are appropriate. It is not the source of operational identity, persistence, ownership, upload history, release state, attempt history, or audit history.

Assessments should be classified by task type rather than by subject identity. A durable assessment record may contain many assessment items, and each item may have its own task type, output type, answer key, rubric mapping, and grading policy. The taxonomy gives those records stable classification terms; the database gives them IDs and lifecycle.

Supported assessment types may include:

- quiz or multiple-choice question
- numeric answer
- short answer
- constructed response
- code assignment
- project
- lab report
- oral explanation
- art or visual critique
- mixed-format task

New assessment types should be added through configuration and clear interfaces, not by changing the platform's core assumptions.

### Taxonomy Mapping

Taxonomy concepts map to operational records as follows:

| Taxonomy concept | Operational use |
| --- | --- |
| Assessment type | Classifies an assessment or assessment item as a task shape such as code assignment, numeric answer, lab report, or project |
| Evidence type | Classifies submitted evidence such as text, numeric value, code, image, archive, or mixed bundle |
| Output type | Describes the expected output or response shape, such as exact answer, executable behavior, report, table, or presentation |
| Rubric type | Describes the scoring structure, such as binary key, checklist, analytic rubric, holistic rubric, or weighted criteria |
| File purpose | Describes why an artifact exists in the workflow, such as assessment material, answer key source, submission evidence, rubric source, or converted Markdown |
| Compatibility rule | Checks whether an assessment type can reasonably pair with an evidence type, output type, or rubric type |

Taxonomy compatibility should prevent obvious mismatches, such as grading an image as a numeric answer unless a subject pack or explicit configuration allows that behavior. Compatibility rules should remain explainable and configurable rather than becoming hidden subject-specific workflows.

### Non-Taxonomy Concerns

IDs, timestamps, ownership, attempts, upload sessions, course releases, grading runs, review tasks, and audit events are not taxonomy concerns. These belong to the database and application lifecycle model.

For example, `code-assignment` is a taxonomy value. A specific assignment named "Python Score Summary", its questions, learner submissions, uploaded files, grading runs, and teacher overrides are persistent records with their own IDs and history.

## Evidence Taxonomy

RubriCore-STE supports different forms of evidence because learning can be demonstrated in many ways.

Supported evidence types may include:

- text
- numeric input
- code
- file upload
- image
- audio
- video
- table data
- mixed evidence bundles

Evidence should be stored in its original form where appropriate, with extracted or normalized representations stored separately for grading, review, and traceability.

Evidence taxonomy should not decide whether a submitted file is valid, correct, late, owned by a learner, attached to a particular assessment, or ready for grading. Those decisions require submission records, artifact records, policy, extraction status, grading context, and audit history.

## Rubric Taxonomy

Rubrics define how work is evaluated. RubriCore-STE should support multiple rubric styles, including:

- **Binary key**: correct or incorrect scoring.
- **Checklist**: required elements are present or absent.
- **Analytic rubric**: multiple criteria scored independently.
- **Holistic rubric**: one overall score based on the whole response.
- **Criterion-weighted rubric**: criteria have explicit weights.

Rubrics should be versioned, explainable, and connected to the evidence they evaluate.

Rubric taxonomy classifies the scoring structure. Published rubric versions, answer key versions, criterion definitions, source materials, and grading results are persistent database records and must remain traceable over time.

## Taxonomy and Persistence Boundary

Taxonomy docs define the vocabulary and compatibility rules for assessment design. Database setup docs define durable identity, provenance, linkage, lifecycle, and auditability.

The boundary should stay clear:

- taxonomy answers "what kind of assessment, evidence, output, or rubric is this?"
- database design answers "which exact assessment, item, learner, submission, artifact, grading run, and review decision is this?"
- subject packs may recommend taxonomy combinations and adapters, but they should not replace durable database relationships
- grading should store both classification context and persistent IDs so future review can explain what was graded and why

## Hybrid Grading Strategy

RubriCore-STE uses a hybrid grading strategy:

- **Deterministic grading** for clear cases such as exact answers, multiple-choice keys, numeric tolerances, schema validation, expected outputs, and code tests.
- **AI-assisted reasoning** for open-ended evaluation, semantic interpretation, partial credit suggestions, ambiguity detection, and draft feedback.
- **Human-in-the-loop review** for low-confidence, ambiguous, high-stakes, disputed, or policy-sensitive cases.

The system should prefer deterministic logic where correctness can be evaluated reliably. AI should support reasoning and feedback, not silently replace teacher authority.

## AI Usage Principles

The AI layer must remain model-agnostic and provider-agnostic.

AI usage should follow these principles:

- AI outputs should be structured and schema-validated.
- AI should suggest scores, feedback, flags, and reasoning rather than silently override grading decisions.
- AI should support draft feedback, answer interpretation, semantic comparison, and ambiguity detection.
- AI provider details should be abstracted behind a stable internal interface.
- The platform should support external API providers in the short term and open-source or self-hosted models in the future.
- AI calls and outputs used in grading should be traceable.
- Failed or invalid AI outputs should not corrupt grading state.

## Human-in-the-Loop Review Policy

Teacher review is required when automated grading is not sufficient or when policy requires human judgment.

The system should create review tasks when:

- confidence is below the configured threshold
- deterministic and AI-assisted results disagree
- evidence is incomplete, unreadable, or mismatched
- the result is near an important scoring boundary
- the assessment is high stakes
- the response is open-ended and requires judgment
- a learner or teacher disputes the result
- quality-control sampling selects the submission

Review workflows should allow teachers to approve, adjust, override, return for regrade, and add explanations.

## Versioning Rules

RubriCore-STE should preserve grading context over time.

Versioning rules:

- Published rubric versions are immutable.
- Published answer key versions are immutable.
- Editing a published rubric creates a new rubric version.
- Editing a published answer key creates a new answer key version.
- Grading results must store the rubric version and answer key version used.
- AI-assisted results should store provider, model, prompt version, schema version, and relevant metadata.
- Historical grading results must not be silently mutated.
- Regrades should create new grading runs with explicit context.

## Auditability and Traceability

Important actions should be logged so that grading decisions can be explained and reviewed.

Audited actions should include:

- rubric creation, editing, publishing, and archiving
- answer key creation, editing, publishing, and archiving
- grading runs
- deterministic grading summaries
- AI calls and validation outcomes
- teacher reviews
- teacher overrides
- regrade requests
- finalization actions
- subject pack changes
- grading policy changes

Traceability should make it possible to answer what was graded, which rubric and answer key were used, which rules or AI outputs contributed, who reviewed or changed the result, and why.

## Subject Pack Concept

Subject packs are portable configuration modules layered on top of the subject-agnostic core.

A subject pack may include:

- default rubric templates
- domain vocabulary
- example responses
- prompt templates
- deterministic grading rules
- evidence adapters
- allowed assessment types
- recommended evidence types
- calibration examples
- feedback style guidance

Subject packs should remain configuration. They should not create hard-coded subject pathways or override the core architecture.

## Knowledge Library and Document Ingestion

RubriCore-STE should support a knowledge library for reusable grading knowledge. Trusted users may provide Markdown files or upload documents and code artifacts that can be converted into Markdown and used to suggest rubric criteria, grading guidance, feedback themes, and other grading-related recommendations.

The knowledge library is one platform feature inside the broader assessment system. It should be connected to rubric authoring and grading assistance, but it must not silently publish rubric criteria or override teacher decisions. Knowledge-derived suggestions should remain explainable and teacher-approved.

Supported uses may include:

- suggesting rubric criteria
- suggesting scoring guidance
- suggesting common feedback themes
- suggesting accepted answer variants
- retrieving relevant grading guidance during review
- enriching subject pack configuration

The library should accept Markdown directly and support conversion from other formats through adapters. Examples include `.md`, `.pdf`, `.doc`, `.docx`, `.txt`, `.rtf`, `.sql`, `.py`, `.js`, `.ts`, notebooks, spreadsheets, structured data files, images with OCR or captions, and archives when they can be safely extracted. This is not a closed list.

Document ingestion should treat files as source artifacts first. Supported adapters may convert source files into Markdown. Unknown formats should be stored with parser status when allowed and routed to review or manual handling when they cannot be interpreted.

Recommended flow:

`upload/import -> source artifact -> detection -> access classification -> Markdown conversion -> validation -> knowledge source version -> derived chunks or summaries -> rubric suggestion or grading assistance -> teacher approval -> audit trail`

Markdown is the preferred normalized knowledge format because it is readable, versionable, and useful for retrieval and AI-assisted workflows. Original source files and converted Markdown should both remain traceable.

Access scope must be enforced for private, organization, course, subject-pack, and public-safe knowledge sources. AI-assisted use of knowledge sources must respect access scope and provider policy.

## Python-First Backend Direction

RubriCore-STE should use a Python-first backend with clean modular boundaries.

The intended backend direction includes:

- FastAPI for the API layer
- PostgreSQL for relational data
- JSONB for flexible rubric, evidence, subject pack, and AI metadata
- SQLAlchemy for database access
- Alembic for migrations
- Pydantic for typed schemas and validation
- an async job queue for grading, AI calls, regrades, and evidence processing
- object storage for uploaded files and large artifacts
- Markdown conversion and knowledge-library ingestion for reusable grading knowledge
- an AI provider abstraction for external APIs and future self-hosted models

Core grading logic should not depend directly on a specific AI vendor, model, database implementation, or web framework.

## What Should Remain Private

Public documentation must not include:

- real student data
- private learner, teacher, school, or organization information
- production credentials, API keys, tokens, or secrets
- private prompts or proprietary grading prompts
- private knowledge library sources
- confidential rubric datasets
- unpublished evaluation datasets
- internal model benchmarks that are not approved for release
- provider contract details or pricing agreements
- security-sensitive infrastructure details
- implementation code that exposes private system behavior
- internal incident reports or review disputes

Public materials should describe the platform's principles and architecture without exposing sensitive operational details.

## What This Is Not

RubriCore-STE is not:

- a subject-specific grading app
- a single-role assessment tool
- a UI-only design system
- a visual style guide
- a monolith tied to one AI vendor
- a system where AI silently owns grading decisions
- a platform where subjects are hard-coded into backend logic

RubriCore-STE is a subject-agnostic, rubric-first assessment core for deterministic grading, AI-assisted reasoning, teacher review, versioned grading context, and auditable decision-making.
