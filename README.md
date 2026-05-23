# RubriCore-STE

RubriCore-STE is a Python-first, subject-agnostic assessment core for rubric-driven grading, teacher review, reusable grading knowledge, and auditable decision-making.

It is built for learning environments where student work may be a selected option, a number, a paragraph, code, a spreadsheet, a document, a visual artifact, or a mixed evidence bundle.

## What It Does

```mermaid
flowchart LR
    A["Assessment item"] --> B["Published rubric version"]
    B --> C["Submitted evidence"]
    C --> D["Deterministic checks"]
    D --> E{"AI allowed and needed?"}
    E -- "No" --> F["Explainable result"]
    E -- "Yes" --> G["Structured AI suggestion"]
    G --> H["Schema validation"]
    H --> F
    F --> I{"Confidence and policy"}
    I -- "Pass" --> J["Finalized result"]
    I -- "Review" --> K["Teacher review task"]
    J --> L["Audit trail"]
    K --> L
```

RubriCore-STE keeps the core workflow deliberately explicit:

1. A learner submits an immutable answer package.
2. The system resolves the exact published rubric and answer-key versions.
3. Deterministic checks run before AI.
4. AI can assist only through a structured, validated boundary.
5. Confidence and policy decide whether a result can finalize or needs teacher review.
6. Results, review decisions, overrides, and superseding are preserved for audit.

## Why It Exists

Most grading systems become brittle when work is open-ended, cross-disciplinary, or partly automated. RubriCore-STE separates core assessment logic from subject-specific assumptions.

| Instead of | RubriCore-STE uses |
| --- | --- |
| Hard-coded subjects | Portable subject packs and taxonomy values |
| One grading method | Deterministic checks, structured AI assistance, and teacher review |
| Hidden scoring changes | Immutable published rubric and answer-key versions |
| File-type guesswork | Purpose-based artifact classification |
| Model-only decisions | Validated outputs, confidence routing, and audit events |
| Rewriting history | New runs, superseded results, and review records |

## Phase 1 Status

Phase 1 is complete as a backend core. The repository now has the durable schema, service logic, public docs, fixtures, and tests needed to prove the central grading workflow.

RubriCore-STE can now create and preserve versioned grading context, accept immutable submitted evidence, run deterministic grading, optionally validate AI-assisted suggestions, route uncertain results to teacher review, finalize or override results, request regrades, and preserve an audit trail.

This is not yet a production application or user-facing grading UI. Later phases should add API/UI surfaces, production auth and permissions, full answer-key authoring, reporting, deployment, and real provider integrations.

## Phase 2 Status

The first Phase 2 backend slice is implemented for the knowledge-library MVP. RubriCore-STE can now register reusable knowledge sources, convert Markdown and plain text into normalized Markdown artifacts, create retrieval-ready chunks, create citation-backed rubric suggestion drafts, and require teacher approval or rejection before accepted suggestions update a mutable rubric draft.

This is still not a production ingestion system or user-facing authoring UI. Rich document parsing, external AI suggestion generation, vector retrieval, production upload sessions, and API surfaces remain later work.

## Current Backend Foundation

The current public backend foundation includes:

| Area | Implemented shape |
| --- | --- |
| Database foundation | SQLAlchemy models, Alembic migration, PostgreSQL-oriented schema |
| Taxonomy | Assessment, evidence, output, rubric, and file-purpose vocabulary |
| Rubrics | Draft rubrics, immutable published versions, materialized criteria, levels, descriptors, and bindings |
| Answer lifecycle | Draft, submitted, superseded, withdrawn, and archived answer packages |
| Evidence | Submission evidence records and artifact provenance model |
| Grading orchestration | Run creation, deterministic scoring, optional AI interaction records, confidence routing, review tasks, and audit events |
| Review | Review task, teacher review, teacher override, finalization, and return-for-regrade behavior |
| Knowledge library | Source registration, local Markdown/plain-text conversion, knowledge chunks, non-vector retrieval candidates, and teacher-approved rubric suggestion drafts |
| Audit trail | Append-only audit records for major Phase 1 lifecycle, grading, review, and rubric-context actions |
| Fixtures | Public-safe synthetic Python score-summary assignment fixture with knowledge-source examples |
| Tests | Unit coverage for taxonomy, rubric framework, answer lifecycle, artifact provenance, grading orchestration, review policy, knowledge-library logic, rubric suggestions, and audit events |

## Repository Map

```text
.
├── app/
│   └── db/
│       ├── models/       # SQLAlchemy domain models
│       └── services/     # Rubric, answer lifecycle, and grading orchestration services
├── alembic/              # Database migrations
├── docs/
│   ├── setup.md
│   ├── design-system.md
│   ├── use-cases-and-case-studies.md
│   └── logic/            # Public architecture and workflow logic
├── private-docs/         # Local/private design docs; ignored by Git
├── scripts/              # Development helper scripts
├── tests/                # Unit tests and synthetic fixtures
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Start Here

| Document | Use it for |
| --- | --- |
| [docs/setup.md](docs/setup.md) | Local environment and database setup |
| [docs/design-system.md](docs/design-system.md) | Product principles and architecture posture |
| [docs/use-cases-and-case-studies.md](docs/use-cases-and-case-studies.md) | User stories, case studies, and workflow sketches |
| [docs/logic/01-setupdb.md](docs/logic/01-setupdb.md) | Persistence, provenance, artifacts, IDs, and audit linkage |
| [docs/logic/02-assessment-taxonomy.md](docs/logic/02-assessment-taxonomy.md) | Subject-agnostic classification and compatibility boundaries |
| [docs/logic/03-rubric-framework.md](docs/logic/03-rubric-framework.md) | Rubric entities, publishing, bindings, and deterministic scoring |
| [docs/logic/04-answer-lifecycle.md](docs/logic/04-answer-lifecycle.md) | Submitted answer package immutability, revisions, regrades, and superseding |
| [docs/logic/05-grading-orchestration.md](docs/logic/05-grading-orchestration.md) | Grading runs, deterministic-first execution, AI validation, confidence routing, and review tasks |
| [docs/logic/06-confidence-policy.md](docs/logic/06-confidence-policy.md) | Confidence bands, routing gates, review escalation, and auditable policy payloads |
| [docs/logic/07-review-policy.md](docs/logic/07-review-policy.md) | Teacher review decisions, overrides, regrade returns, finalization, and audit trail |
| [docs/logic/08-audit-logging.md](docs/logic/08-audit-logging.md) | Append-only audit events, traceability coverage, and Phase 1 audit boundaries |
| [docs/logic/09-knowledge-library.md](docs/logic/09-knowledge-library.md) | Knowledge source registration, conversion, chunking, retrieval candidates, rubric suggestions, and teacher decisions |

## Quick Start

Create the environment:

```sh
git clone <repository-url>
cd RubriCore-STE
uv sync --dev
cp .env.example .env
```

Apply migrations after PostgreSQL is configured:

```sh
uv run alembic upgrade head
```

Seed local synthetic development data:

```sh
uv run python scripts/seed_dev.py
```

Run tests and linting:

```sh
.venv/bin/pytest
.venv/bin/ruff check .
```

Optional development checks:

```sh
uv run ruff format .
uv run pyright
uv run pre-commit run --all-files
```

Install Git hooks once per clone:

```sh
uv run pre-commit install
```

Package the public backend, tests, and docs for low-token AI review:

```sh
npx repomix --config repomix.config.json
```

## Core Concepts

| Concept | Purpose |
| --- | --- |
| `Assessment` and `AssessmentItem` | Durable authored task context |
| `Submission` | Learner answer package; immutable after submission |
| `SubmissionEvidence` | Typed answer evidence, raw text, value payload, or file-backed artifact link |
| `RubricVersion` | Immutable published rubric snapshot used for grading |
| `AnswerKeyVersion` | Immutable published answer-key snapshot when deterministic key checks apply |
| `GradingRun` | One execution attempt against a submission and fixed grading context |
| `GradingResult` | Proposed, finalized, reviewed, overridden, or superseded outcome |
| `CriterionResult` | Criterion-level score, explanation, source, and confidence |
| `AIInteraction` | Provider/model/prompt/schema trace for AI-assisted evaluation |
| `ReviewTask` | Teacher-facing queue item for low-confidence, ambiguous, disputed, or policy-sensitive results |
| `KnowledgeSource` | Versioned reusable grading knowledge linked to source and converted Markdown artifacts |
| `KnowledgeChunk` | Deterministic Markdown-derived retrieval and citation unit |
| `RubricSuggestion` | Citation-backed draft recommendation that requires teacher decision before changing a rubric draft |
| `AuditEvent` | Append-only history of important lifecycle and grading transitions |

## Implementation Posture

RubriCore-STE favors plain, auditable service logic over hidden workflow magic.

- deterministic checks run before AI
- AI output must be structured and validated
- published rubric and answer-key versions are immutable
- submitted evidence is not edited in place
- low-confidence or policy-exception cases route to teacher review
- regrades create new runs rather than rewriting old results
- final displayed outcomes should come from non-superseded finalized, reviewed, or overridden results

## Knowledge-Learning Loop

Teacher-added knowledge should make future grading setup better, but it should never silently become grading authority.

```mermaid
flowchart TD
    A["Teacher uploads guidance"] --> B["Store source artifact"]
    B --> C["Convert to Markdown when supported"]
    C --> D["Create versioned knowledge source"]
    D --> E["Retrieve relevant chunks"]
    E --> F["Suggest rubric criteria or grading guidance"]
    F --> G{"Teacher decision"}
    G -- "Accept or edit" --> H["Add to draft"]
    G -- "Reject" --> I["Record rejection"]
    H --> J["Publish through normal versioning"]
    I --> K["Audit trail"]
    J --> K
```

## Repository Readiness

Tracked files are intended to be public-safe: source code, migrations, setup files, public docs, and synthetic fixtures. Local caches, virtual environments, `.env`, private docs, private fixtures, local artifacts, and database dumps are ignored.

The project uses the MIT License. Before a broader public release, consider adding a lightweight project-specific contribution policy.

## Roadmap

| Horizon | Focus |
| --- | --- |
| Phase 1 | Complete: core database foundation, deterministic grading, grading orchestration, review tasks, overrides, and audit trail |
| Phase 2 | In progress: knowledge-library backend MVP implemented; pilot API/UI, richer import workflows, and provider integrations remain |
| Phase 3 | Evaluation datasets, calibration, reliability metrics, and model/prompt regression testing |
| Phase 4 | Provider routing, fallback policy, scale-out, and batch grading |
| Phase 5 | Self-hosted AI evaluation and deployment options |

## Data Safety

Only synthetic sample data belongs in public files.

Do not commit real student work, private prompts, private rubrics, private knowledge-library sources, unpublished evaluation datasets, production credentials, or sensitive school and learner information.

## Contributing Principles

- keep the platform subject-agnostic
- keep published grading context immutable
- keep AI output structured, validated, and traceable
- keep teacher review visible and auditable
- keep private data out of public docs and fixtures
- prefer small, well-scoped changes that fit the existing architecture

## License

RubriCore-STE is licensed under the [MIT License](LICENSE).
