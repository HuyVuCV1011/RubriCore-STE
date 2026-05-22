# Setup Database Logic

This document describes the public database setup logic for RubriCore-STE. It focuses on persistence, provenance, linkage, lifecycle state, and auditability. For local installation commands, see [Setup Guide](../setup.md).

## Database Setup

RubriCore-STE is designed to use PostgreSQL as the primary database.

For local development, either:

- run PostgreSQL locally, or
- run PostgreSQL through Docker Compose

Docker is the preferred option for contributors because it avoids local database version drift.

Create a local environment file from the example template:

```sh
cp .env.example .env
```

Then set a local development database URL, for example:

```sh
DATABASE_URL=postgresql+psycopg://rubricore:rubricore@localhost:5432/rubricore_ste
```

Do not commit real credentials or private environment files.

## Migrations

RubriCore-STE uses Alembic for database migrations.

Apply migrations with:

```sh
alembic upgrade head
```

Migration files should be reviewed like application code because they define durable grading and audit history.

For local development only, seed generic setup records with:

```sh
python scripts/seed_dev.py
```

Seed data must stay synthetic and should not include real learner records, private rubrics, private prompts, credentials, or provider secrets.

## Evidence Artifacts

RubriCore-STE stores uploaded or imported files outside relational database rows. PostgreSQL should store artifact metadata, purpose classification, storage references, parser status, extraction status, and normalized representations needed for grading and review.

File extension and MIME type should not determine a file's role by themselves. Prompt materials, answer key sources, learner submissions, reference solutions, and extracted representations should be tracked by explicit purpose metadata.

Knowledge-library inputs follow the same artifact-first rule. Markdown files can be used directly, while supported document, note, code, spreadsheet, image, or archive formats may later be converted into Markdown for rubric suggestions and grading guidance. Unsupported formats should remain stored artifacts with parser status rather than being silently discarded.

## Database Identity and Linkage

The database is responsible for durable identity, provenance, linkage, lifecycle state, and audit history. Taxonomy values classify records, but database IDs identify the exact records involved in authoring, submission, grading, review, and audit.

Core identity and linkage expectations:

| Entity or field | Purpose |
| --- | --- |
| `assessment.id` | Durable identity for an authored assessment, assignment, quiz, project, or task collection |
| `assessment_item.id` | Durable identity for a specific problem, question, prompt, or task inside an assessment |
| `submission.id` | Durable identity for a learner's submitted response package or future attempt |
| `learner_id` | Links a submission to the learner whose work is being evaluated |
| `file_artifact.id` | Durable identity for an uploaded, imported, generated, converted, or extracted file artifact |
| `submission_evidence.file_artifact_id` | Links submitted evidence to the stored artifact when evidence is file-backed |
| `file_artifact.owner_user_id` | Optional user responsible for or controlling the artifact after intake |
| `file_artifact.uploaded_by_user_id` | Optional user or actor who performed the upload or import action |
| `file_artifact.source_type` | Controlled workflow source such as `web_upload`, `fixture_import`, `teacher_import`, `api_import`, `batch_import`, `system_conversion`, or `knowledge_library` |
| `file_artifact.source_format` | Controlled normalized processing format such as `python`, `markdown`, `pdf`, `docx`, `csv`, `image`, `archive`, or `unknown` |
| `rubric_version_id` | Records the exact published rubric version used for grading |
| `rubric_binding.id` | Records which published rubric version is attached to an assessment, assessment item, or evaluation context |
| `rubric_criterion.id` | Durable identity for an ordered criterion inside a published rubric version |
| `performance_level.id` | Durable identity for an ordered score band inside a published rubric version |
| `rubric_descriptor.id` | Durable identity for the narrative expectations at one criterion x performance-level pair |
| `answer_key_version_id` | Records the exact published answer key version used for grading |
| `created_at` and `updated_at` | Record persistence timestamps for database rows |
| `uploaded_at` | Records when an artifact was received by the platform or import process |
| `submitted_at` | Records when learner work was submitted when that differs from row creation |
| `storage_uri` | Points to the object-storage or fixture location of file bytes outside the relational row |
| `metadata_payload` | Holds flexible metadata while the stable schema is still evolving |

For web-based submission, each assessment should have its own ID, each assessment item should have its own ID, and each learner submission should link back to the relevant assessment or assessment item. This allows grading, regrading, review, analytics, and audit history to answer which exact task and learner evidence were evaluated.

File and artifact records should preserve upload/import metadata such as source type, source format, uploader or owner, access scope, checksum, parser status, conversion status, and storage reference. Some of these fields are stable columns now; others may start in `metadata_payload` and become first-class columns when the workflow hardens.

`owner_user_id` and `uploaded_by_user_id` are intentionally separate. The owner is responsible for or controls the artifact after intake. The uploader is the actor who caused the artifact to enter the system. They may be the same user, different users, or null in MVP flows where ownership is inferred through submission and learner context.

`source_format` is not a replacement for MIME type or file extension. MIME type and extension are raw observed descriptors; source format is the normalized format used for adapter routing and processing decisions. File purpose still describes why the artifact matters in the assessment workflow.

`uploaded_at` is distinct from `created_at`. In normal web-upload paths they will usually match, but they can differ for backfills, external imports, retry processing, or reconstructed records.

## MVP Web Upload and Provenance Flow

The MVP web-upload flow should be:

`web upload or import -> FileArtifact with provenance -> SubmissionEvidence link -> EvidenceExtraction or ArtifactConversion -> GradingRun -> GradingResult -> ReviewTask or AuditEvent`

In this flow, `FileArtifact` stores artifact identity, storage metadata, provenance, access scope, and parser/conversion status. `SubmissionEvidence` remains the canonical MVP bridge between a learner submission and the stored artifact.

`FileArtifact` should not absorb future upload-session logic. Chunking, resumability, staged multi-file package assembly, virus scanning queues, browser session IDs, retry orchestration, and temporary upload state belong to a future `UploadSession` or processing-job layer when those workflows become necessary.

## Conceptual Entity Chain

The long-term conceptual chain is:

`Organization -> Course/ClassSection -> Assessment or Assignment -> AssessmentItem / Problem / Question -> RubricBinding -> Published RubricVersion + AnswerKeyVersion -> Learner -> Submission or Attempt -> SubmissionEvidence -> FileArtifact -> EvidenceExtraction / ArtifactConversion -> GradingRun -> GradingResult -> CriterionResult -> ReviewTask / AuditEvent`

MVP-now layers:

- `Organization`
- `Assessment`
- `AssessmentItem`
- `RubricVersion`
- `RubricCriterion`
- `PerformanceLevel`
- `RubricDescriptor`
- `RubricBinding`
- `AnswerKeyVersion`
- `Learner`
- `Submission`
- `SubmissionEvidence`
- `FileArtifact`
- `EvidenceExtraction`
- `ArtifactConversion`
- `GradingRun`
- `GradingResult`
- `CriterionResult`
- `ReviewTask`
- `AuditEvent`

Future-expansion layers:

- `Course` or `ClassSection`, for classroom membership, roster scoping, release windows, and course-level permissions
- `Assignment` or `AssessmentRelease`, when the same authored assessment can be released to multiple classes, cohorts, or due-date windows
- `Attempt`, when learners can save drafts, submit multiple tries, retake quizzes, or receive separate grading histories per try
- `UploadSession`, when large or multi-file web uploads need resumability, virus scanning, package validation, or staged processing
- explicit artifact owner/uploader fields, when web upload flows need stronger provenance than generic metadata

## Taxonomy Boundary

Assessment taxonomy belongs in [Assessment Taxonomy Logic](02-assessment-taxonomy.md) because it defines classification and compatibility: assessment type, evidence type, output type, rubric type, file purpose, and subject-pack recommendations. Rubric scoring structure and lifecycle details belong in [Rubric Framework Logic](03-rubric-framework.md).

Database setup belongs here because it defines persistence: IDs, timestamps, ownership, storage references, foreign-key links, status fields, lifecycle transitions, grading context, review history, and audit events.

Future implementation should preserve these boundaries. A taxonomy value such as `code-assignment` should help validate that code evidence and checklist or analytic rubrics are compatible. It should not replace `assessment.id`, `assessment_item.id`, `submission.id`, `file_artifact.id`, `rubric_binding.id`, or the rubric and answer key version IDs used for grading.

## Safe Bootstrapping Guidelines

Public bootstrapping should use only:

- synthetic sample data
- generic assessment types
- generic evidence types
- generic rubric examples
- local development credentials

Do not include:

- real student data
- private prompts
- production credentials
- API keys
- private rubric datasets
- unpublished evaluation datasets
- sensitive school, learner, teacher, or organization information
- private knowledge-library sources
