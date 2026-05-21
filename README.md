# RubriCore-STE

RubriCore-STE is a Python-first, subject-agnostic assessment platform core for evaluating student work across multiple disciplines. It is built around assessment types, evidence types, rubric types, and subject pack configuration rather than fixed subject roles or hard-coded discipline logic.

## Product Direction

RubriCore-STE is designed for trustworthy grading workflows across subjects such as Data, Programming, Math, Physics, Art, and future subject packs.

Core concepts:

- Assessment types define the nature of the task.
- Evidence types define the form of student work.
- Rubric types define the scoring structure.
- Subject packs provide portable configuration.
- Deterministic grading handles clear right/wrong cases.
- AI assists with open-ended reasoning, ambiguity detection, and feedback drafts.
- Teacher review handles low-confidence, high-stakes, ambiguous, or disputed cases.

## Current Status

This repository is in early Phase 1 development.

Current public-facing foundation includes:

- Python backend setup direction
- PostgreSQL/Alembic database foundation
- public setup documentation
- public product/system design documentation
- initial project structure for backend development

The project is not yet a complete production application.

## Architecture Summary

RubriCore-STE is intended to use:

- FastAPI for the API layer
- PostgreSQL for durable relational data
- JSONB for flexible rubric, evidence, subject pack, and AI metadata
- SQLAlchemy for database access
- Alembic for migrations
- Pydantic for typed validation
- async jobs for grading, AI calls, evidence processing, and regrades
- object storage references for uploaded or imported evidence artifacts
- a model-agnostic AI provider abstraction

Evidence files should be treated as generic artifacts first and parsed evidence second. The system should preserve original files, track metadata and parser status, and support review escalation when evidence cannot be safely interpreted.

## Repository Structure

```text
.
├── app/                  # Python backend application package
├── alembic/              # Database migration setup
├── docs/                 # Public documentation
│   ├── design-system.md  # Product and system design principles
│   └── setup.md          # Public development setup guide
├── scripts/              # Development helper scripts
├── tests/                # Test fixtures and future tests
├── .env.example          # Local environment template
├── alembic.ini           # Alembic configuration
├── requirements.txt      # Python dependencies
└── README.md
```

## Getting Started

See [docs/setup.md](docs/setup.md) for the full public setup guide.

Recommended development approach:

- use a local Python environment for application development
- use Docker for infrastructure services such as PostgreSQL
- keep real credentials, private prompts, and real learner data out of the repository

Basic local setup:

```sh
git clone <repository-url>
cd RubriCore-STE

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Apply database migrations once PostgreSQL is configured:

```sh
alembic upgrade head
```

Seed local development records:

```sh
python scripts/seed_dev.py
```

## Sample and Demo Data

Only synthetic sample data should be committed to this repository.

Real student work, private prompts, private rubrics, unpublished evaluation datasets, production credentials, and sensitive school or learner information must stay out of public files.

## Roadmap

Near-term work:

- expand the Phase 1 backend domain model
- strengthen assessment, evidence, rubric, and answer key workflows
- implement deterministic grading for clear cases
- add AI provider abstraction with structured output validation
- add teacher review, override, and audit workflows
- build tests around grading lifecycle and database integrity

Longer-term direction:

- subject pack configuration
- evaluation and calibration pipeline
- provider routing and fallback
- future support for open-source or self-hosted AI models

## Contributing

Contributions should preserve the core architecture:

- keep the platform subject-agnostic
- avoid hard-coded discipline or role assumptions
- prefer explainable, auditable grading behavior
- validate AI outputs before using them
- use synthetic data in tests and examples
- avoid committing secrets or real learner data

See [docs/design-system.md](docs/design-system.md) for the public design principles.
