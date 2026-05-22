# RubriCore-STE Setup Guide

This guide describes the recommended public development setup for RubriCore-STE.

RubriCore-STE is a Python-first assessment platform core. The recommended development approach is **hybrid**:

- use a local Python environment for application development
- use Docker for infrastructure services such as PostgreSQL

This keeps Python development fast and familiar while making shared services reproducible across machines.

## Recommended Setup Approach

### Hybrid Development

Use local Python for:

- FastAPI application code
- domain models and services
- Pydantic schemas
- SQLAlchemy database access
- tests and development tooling

Use Docker for:

- PostgreSQL
- optional Redis or job queue dependencies when introduced
- optional object-storage-compatible services when introduced

Docker is recommended for service dependencies, but the application itself does not need to run inside Docker during early development.

## Prerequisites

Install:

- Python 3.11 or newer
- PostgreSQL 15 or newer, either local or through Docker
- Git
- Docker and Docker Compose, recommended for local services

Optional tools:

- `make`, if project commands are later wrapped in a Makefile
- `uv`, `poetry`, or standard `venv` for Python dependency management

## Local Development Steps

Clone the repository:

```sh
git clone <repository-url>
cd RubriCore-STE
```

Create and activate a Python virtual environment:

```sh
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```sh
pip install -r requirements.txt
```

If the project uses another dependency manager later, follow the command documented by that tool.

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

`Organization -> Course/ClassSection -> Assessment or Assignment -> AssessmentItem / Problem / Question -> Published RubricVersion + AnswerKeyVersion -> Learner -> Submission or Attempt -> SubmissionEvidence -> FileArtifact -> EvidenceExtraction / ArtifactConversion -> GradingRun -> GradingResult -> CriterionResult -> ReviewTask / AuditEvent`

MVP-now layers:

- `Organization`
- `Assessment`
- `AssessmentItem`
- `RubricVersion`
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

Assessment taxonomy belongs in the design docs because it defines classification and compatibility: assessment type, evidence type, output type, rubric type, file purpose, and subject-pack recommendations.

Database setup belongs here because it defines persistence: IDs, timestamps, ownership, storage references, foreign-key links, status fields, lifecycle transitions, grading context, review history, and audit events.

Future implementation should preserve both sides of the boundary. A taxonomy value such as `code-assignment` should help validate that code evidence and checklist or analytic rubrics are compatible. It should not replace `assessment.id`, `assessment_item.id`, `submission.id`, `file_artifact.id`, or the rubric and answer key version IDs used for grading.

## Running the Application

Once the FastAPI application entrypoint is available, run the development server with the documented project command, typically similar to:

```sh
uvicorn app.main:app --reload
```

The exact command may change as the project structure matures.

## Running Tests

Once test tooling is available, run tests with:

```sh
pytest
```

Tests should avoid real student data and should use synthetic fixtures.

## Docker Policy

Docker is:

- recommended for PostgreSQL and future infrastructure dependencies
- optional for running the Python application during early development
- useful for repeatable contributor environments

Docker is not required as the only way to run the project. Contributors should be able to develop the Python application locally as long as required services are available.

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

## Current Status

This repository is in early setup. The backend database foundation, dependency file, Alembic migration tooling, and local development seed command are available.

Public setup documentation should stay concise and safe to publish. Internal planning details should remain outside public docs.
