# Knowledge Library Logic

This document describes the public Phase 2 knowledge-library backend logic for RubriCore-STE. It focuses on source registration, local Markdown conversion, chunking, non-vector retrieval, rubric suggestion drafts, teacher decisions, provenance, and rubric immutability.

The knowledge library helps teachers reuse grading guidance. It is not a grading authority and does not silently change published rubrics, answer keys, grading results, or learner submissions.

## Implemented Entities

| Entity | Purpose |
| --- | --- |
| `KnowledgeSource` | Versioned source item linked to an original file artifact and optional converted Markdown artifact |
| `KnowledgeChunk` | Deterministic Markdown-derived chunk used for retrieval candidates and source citations |
| `RubricSuggestion` | Draft recommendation for rubric authoring with source citations and teacher decision state |
| `FileArtifact` | Original source artifact or converted Markdown artifact |
| `ArtifactConversion` | Trace of a source-to-Markdown conversion attempt |
| `AuditEvent` | Append-only lifecycle and decision history |

## Scope Boundary

The current backend slice supports:

- artifact-first knowledge source registration
- access-scope normalization
- Markdown passthrough conversion
- plain-text to Markdown conversion
- explicit unsupported or failed conversion status
- Markdown chunk creation with heading paths, stable positions, content hashes, and citations
- retrieval-ready non-vector candidate selection through scoped filtering and deterministic text matching
- rubric suggestion draft creation with citations
- teacher acceptance, edited acceptance, rejection, and superseding of suggestions
- draft rubric updates from accepted suggestions
- audit events for material transitions
- public-safe fixture and seed support

The current backend slice does not include:

- production upload sessions
- full document parsing for PDF, DOCX, spreadsheets, images, or archives
- embeddings or vector search
- external AI provider calls for suggestion generation
- public API endpoints or UI
- automatic published rubric mutation
- automatic answer-key mutation

## Knowledge Registration

Knowledge registration creates source identity before conversion or retrieval.

The registration service creates a `FileArtifact` with purpose `knowledge_source`, source format, source type, access scope, owner/uploader where available, and storage reference. It then creates a `KnowledgeSource` linked to that artifact.

Supported local formats are marked ready for conversion. Unsupported formats remain stored artifacts with `unsupported` conversion status rather than causing intake to fail.

## Local Conversion

Markdown is the normalized knowledge format for Phase 2.

The local converter supports:

- Markdown passthrough for `.md` and `.markdown`
- plain-text normalization for `.txt`

Converted Markdown is stored as a derived `FileArtifact` with purpose `converted_markdown`. The original source artifact remains unchanged. Every conversion attempt records an `ArtifactConversion` row.

Unsupported or failed conversions block chunking for that source version but do not delete the original artifact.

## Chunking

Chunks are deterministic citation units derived from converted Markdown.

The chunking helper:

- splits by Markdown headings first
- preserves heading paths
- keeps stable positions
- stores content hashes
- tracks character counts
- preserves content text for retrieval and citations
- returns existing active chunks when the same source version is chunked again with identical content
- requires explicit replacement before superseding active chunks with changed content

Chunks are available for retrieval only when active. Unsupported sources do not produce chunks.

## Non-Vector Retrieval

The current retrieval helper is relational and deterministic.

It filters by:

- organization
- active source and chunk status
- allowed access scopes
- optional selected source IDs

It ranks candidates with simple explainable text matching against chunk content and heading paths. This keeps the Phase 2 MVP testable without embeddings or vector infrastructure.

## Rubric Suggestions

Rubric suggestions are draft records. Creating a suggestion does not mutate a rubric.

Each suggestion records:

- target rubric
- optional assessment or assessment item context
- suggestion type
- payload
- source citations
- status
- creator and reviewer fields where available
- decision reason and accepted payload when reviewed

Suggestions require source citations so teachers and auditors can trace where the recommendation came from.

## Teacher Decisions

Teachers or trusted reviewers can:

- accept a suggestion as-is
- accept a suggestion with edits
- reject a suggestion with a reason
- supersede a draft suggestion

Acceptance validates the resulting rubric draft schema. Rejection preserves the original suggestion and records the reason.

## Rubric Immutability

Accepted suggestions update only `Rubric.draft_schema`. They do not update any `RubricVersion`, materialized published criteria, published descriptors, grading runs, grading results, or answer keys.

To make accepted suggestion content usable for grading, a teacher must publish a new rubric version through the normal rubric framework.

## Audit and Provenance

The backend emits audit events for:

- knowledge source registration
- successful conversion
- unsupported or failed conversion
- chunk creation
- suggestion creation
- suggestion acceptance
- suggestion rejection
- suggestion superseding
- rubric draft updates from accepted suggestions

The intended provenance chain is:

`source artifact -> conversion attempt -> converted Markdown artifact -> knowledge source -> chunks -> suggestion -> teacher decision -> rubric draft -> future published rubric version`

## Fixture and Seed Expectations

Public fixtures must remain synthetic and public-safe.

The Python score-summary fixture may include teacher guidance, misconception notes, rubric suggestion seed material, and plain-text conversion sources. Local seed can register these as public-safe knowledge sources, convert supported files, and create chunks for development and regression tests.

Seed data must not include real learner records, private prompts, private rubrics, credentials, or private knowledge sources.
