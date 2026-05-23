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

RubriCore-STE is designed to use PostgreSQL as the primary database. For local development, run PostgreSQL locally or through Docker Compose.

Create a local environment file from the example template:

```sh
cp .env.example .env
```

Then set a local development `DATABASE_URL`. Do not commit real credentials or private environment files.

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

Seed data must stay synthetic and should not include real learner records, private rubrics, private prompts, credentials, provider secrets, or private knowledge sources. The current development seed may register public-safe fixture knowledge sources, convert supported Markdown or plain-text sources, and create chunks for local regression coverage.

For the public database model, artifact provenance, entity chain, and taxonomy boundary, see [Setup Database Logic](logic/01-setupdb.md).

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

## Current Status

This repository is in early setup. The backend database foundation, dependency file, Alembic migration tooling, local development seed command, core grading workflow, review policy, and knowledge-library backend MVP are available.

Public setup documentation should stay concise and safe to publish. Internal planning details should remain outside public docs.
