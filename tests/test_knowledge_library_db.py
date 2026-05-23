import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import FileArtifact, FilePurpose, KnowledgeSource, Organization
from app.db.services.knowledge_library import (
    create_knowledge_chunks,
    retrieve_candidate_chunks,
)


@pytest.fixture
def db_session() -> Iterator[Session]:
    try:
        database_url = get_settings().database_url
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            required_tables = {
                "organizations",
                "file_purposes",
                "file_artifacts",
                "knowledge_sources",
                "knowledge_chunks",
            }
            existing_tables = set(inspect(connection).get_table_names())
            if not required_tables.issubset(existing_tables):
                missing = ", ".join(sorted(required_tables - existing_tables))
                pytest.skip(f"Database is not migrated for Phase 2 knowledge-library tests; missing: {missing}")
            if connection.in_transaction():
                connection.rollback()

            transaction = connection.begin()
            session = Session(bind=connection)
            try:
                yield session
            finally:
                session.close()
                transaction.rollback()
    except OperationalError as exc:
        pytest.skip(f"Database-backed knowledge-library tests require a reachable dev database: {exc}")


def _seed_source(db: Session, *, source_title: str, content_label: str) -> KnowledgeSource:
    organization = Organization(
        name=f"DB Test Org {uuid.uuid4()}",
        slug=f"db-test-{uuid.uuid4()}",
        status="active",
    )
    db.add(organization)
    db.flush()

    knowledge_purpose = FilePurpose(
        organization_id=organization.id,
        key=f"knowledge_source_{uuid.uuid4()}",
        name="Knowledge Source",
        config={},
        status="active",
    )
    markdown_purpose = FilePurpose(
        organization_id=organization.id,
        key=f"converted_markdown_{uuid.uuid4()}",
        name="Converted Markdown",
        config={},
        status="active",
    )
    db.add_all([knowledge_purpose, markdown_purpose])
    db.flush()

    source_artifact = FileArtifact(
        organization_id=organization.id,
        file_purpose_id=knowledge_purpose.id,
        original_filename=f"{content_label}.md",
        normalized_filename=f"{content_label}.md",
        file_extension="md",
        mime_type="text/markdown",
        detected_file_category="document",
        storage_uri=f"test://{content_label}.md",
        import_source="fixture_import",
        source_type="fixture_import",
        source_format="markdown",
        access_scope="public_safe",
        parser_support_status="supported",
        status="active",
        metadata_payload={},
    )
    converted_artifact = FileArtifact(
        organization_id=organization.id,
        file_purpose_id=markdown_purpose.id,
        original_filename=f"{content_label}.md",
        normalized_filename=f"{content_label}.md",
        file_extension="md",
        mime_type="text/markdown",
        detected_file_category="document",
        storage_uri=f"derived://{content_label}.md",
        import_source="knowledge_library_conversion",
        source_type="system_conversion",
        source_format="markdown",
        access_scope="public_safe",
        parser_support_status="supported",
        status="active",
        metadata_payload={},
    )
    db.add_all([source_artifact, converted_artifact])
    db.flush()

    source = KnowledgeSource(
        organization_id=organization.id,
        source_file_artifact_id=source_artifact.id,
        converted_markdown_artifact_id=converted_artifact.id,
        title=source_title,
        version_number=1,
        access_scope="public_safe",
        conversion_status="converted",
        status="active",
        metadata_payload={},
    )
    db.add(source)
    db.flush()
    return source


def test_db_chunk_creation_is_idempotent_for_same_content(db_session: Session) -> None:
    source = _seed_source(db_session, source_title="DB Teacher Notes", content_label="teacher-notes")
    content = "# Teacher Notes\n\nInclude scores equal to the passing threshold."

    first_chunks = create_knowledge_chunks(db_session, knowledge_source=source, markdown_content=content)
    second_chunks = create_knowledge_chunks(db_session, knowledge_source=source, markdown_content=content)

    assert [chunk.id for chunk in second_chunks] == [chunk.id for chunk in first_chunks]
    assert len(second_chunks) == 1


def test_db_retrieval_respects_scope_and_source_filters(db_session: Session) -> None:
    source = _seed_source(db_session, source_title="DB Misconceptions", content_label="misconceptions")
    create_knowledge_chunks(
        db_session,
        knowledge_source=source,
        markdown_content="# Misconceptions\n\nStudents often miss threshold equality.",
    )

    matches = retrieve_candidate_chunks(
        db_session,
        organization_id=source.organization_id,
        query="threshold equality",
        allowed_access_scopes={"public_safe"},
        source_ids={source.id},
    )
    blocked = retrieve_candidate_chunks(
        db_session,
        organization_id=source.organization_id,
        query="threshold equality",
        allowed_access_scopes={"private"},
        source_ids={source.id},
    )

    assert len(matches) == 1
    assert matches[0].matched_terms == ["threshold", "equality"]
    assert blocked == []
