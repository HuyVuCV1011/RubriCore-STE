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

## Current Status

This repository is in early setup. The backend database foundation, dependency file, Alembic migration tooling, and local development seed command are available.

Public setup documentation should stay concise and safe to publish. Internal planning details should remain outside public docs.
