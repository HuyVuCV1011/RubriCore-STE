import uuid

import pytest
from sqlalchemy import CheckConstraint

from app.db.models import ArtifactConversion, AuditEvent, FilePurpose, KnowledgeChunk, KnowledgeSource, RubricSuggestion
from app.db.services.knowledge_library import (
    KnowledgeLibraryError,
    build_markdown_chunk_drafts,
    convert_knowledge_source_to_markdown,
    create_knowledge_chunks,
    register_knowledge_source,
)


class RecordingSession:
    def __init__(self, *, scalar_results: list[object | None] | None = None) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.scalar_results = list(scalar_results or [])
        self.scalars_results: list[object] = []

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        self.flush_count += 1
        for record in self.added:
            if hasattr(record, "id") and record.id is None:
                record.id = uuid.uuid4()

    def scalar(self, _: object) -> object | None:
        if not self.scalar_results:
            return None
        return self.scalar_results.pop(0)

    def scalars(self, _: object) -> list[object]:
        return self.scalars_results


def file_purpose(key: str) -> FilePurpose:
    return FilePurpose(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        key=key,
        name=key.replace("_", " ").title(),
        config={},
        status="active",
    )


def records(session: RecordingSession, record_type: type) -> list:
    return [record for record in session.added if isinstance(record, record_type)]


def test_phase_2_knowledge_models_are_registered() -> None:
    assert KnowledgeChunk.__tablename__ == "knowledge_chunks"
    assert RubricSuggestion.__tablename__ == "rubric_suggestions"

    chunk_constraints = {
        str(constraint.sqltext)
        for constraint in KnowledgeChunk.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    suggestion_constraints = {
        str(constraint.sqltext)
        for constraint in RubricSuggestion.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "status in ('active', 'superseded', 'archived')" in chunk_constraints
    assert "status in ('draft', 'accepted', 'rejected', 'superseded')" in suggestion_constraints


def test_register_knowledge_source_is_artifact_first_and_audited() -> None:
    organization_id = uuid.uuid4()
    session = RecordingSession(scalar_results=[file_purpose("knowledge_source")])

    source = register_knowledge_source(
        session,  # type: ignore[arg-type]
        organization_id=organization_id,
        title="Teacher Notes",
        source_filename="notes.md",
        source_storage_uri="fixture://notes.md",
        access_scope="public-safe",
        source_type="fixture_import",
    )

    assert source.organization_id == organization_id
    assert source.access_scope == "public_safe"
    assert source.conversion_status == "pending"
    assert source.status == "draft"
    assert source.metadata_payload["source_format"] == "markdown"
    assert records(session, AuditEvent)[0].action == "knowledge_source.registered"


def test_text_conversion_creates_markdown_artifact_and_conversion_record() -> None:
    organization_id = uuid.uuid4()
    source = KnowledgeSource(
        id=uuid.uuid4(),
        organization_id=organization_id,
        source_file_artifact_id=uuid.uuid4(),
        title="Common Misconceptions",
        access_scope="public_safe",
        conversion_status="pending",
        status="draft",
        metadata_payload={"source_format": "text"},
    )
    session = RecordingSession(scalar_results=[file_purpose("converted_markdown")])

    markdown_artifact = convert_knowledge_source_to_markdown(
        session,  # type: ignore[arg-type]
        knowledge_source=source,
        source_filename="misconceptions.txt",
        source_content="Students may exclude scores equal to the threshold.",
    )

    assert markdown_artifact is not None
    assert markdown_artifact.source_format == "markdown"
    assert source.conversion_status == "converted"
    assert source.status == "active"
    assert source.converted_markdown_artifact_id == markdown_artifact.id
    conversion = records(session, ArtifactConversion)[0]
    assert conversion.conversion_status == "completed"
    assert conversion.converter_name == "plain_text_to_markdown"
    assert records(session, AuditEvent)[0].action == "knowledge_source.converted"


def test_unsupported_conversion_is_preserved_without_chunks() -> None:
    source = KnowledgeSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_file_artifact_id=uuid.uuid4(),
        title="Slides",
        access_scope="organization",
        conversion_status="pending",
        status="draft",
        metadata_payload={"source_format": "pdf"},
    )
    session = RecordingSession()

    output = convert_knowledge_source_to_markdown(
        session,  # type: ignore[arg-type]
        knowledge_source=source,
        source_filename="slides.pdf",
        source_content="ignored",
    )

    assert output is None
    assert source.conversion_status == "unsupported"
    assert records(session, ArtifactConversion)[0].conversion_status == "unsupported"
    assert records(session, AuditEvent)[0].action == "knowledge_source.conversion_unsupported"

    with pytest.raises(KnowledgeLibraryError, match="converted Markdown"):
        create_knowledge_chunks(session, knowledge_source=source, markdown_content="ignored")  # type: ignore[arg-type]


def test_markdown_chunking_preserves_headings_and_code_fences() -> None:
    markdown = """# Grading Notes

Students should include threshold scores.

## Code Evidence

```python
def score_report(scores):
    return {}
```
"""

    drafts = build_markdown_chunk_drafts(markdown, max_characters=80)

    assert [draft.position for draft in drafts] == list(range(len(drafts)))
    assert drafts[0].heading_path == ["Grading Notes"]
    assert any("```python" in draft.content for draft in drafts)
    assert all(draft.content_hash for draft in drafts)


def test_create_knowledge_chunks_records_active_chunks_and_audit() -> None:
    source = KnowledgeSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_file_artifact_id=uuid.uuid4(),
        converted_markdown_artifact_id=uuid.uuid4(),
        title="Teacher Notes",
        access_scope="public_safe",
        conversion_status="converted",
        status="active",
        metadata_payload={},
    )
    session = RecordingSession()

    chunks = create_knowledge_chunks(
        session,  # type: ignore[arg-type]
        knowledge_source=source,
        markdown_content="# Notes\n\nInclude equality at the passing threshold.",
    )

    assert len(chunks) == 1
    assert chunks[0].status == "active"
    assert chunks[0].heading_path == ["Notes"]
    assert records(session, AuditEvent)[0].action == "knowledge_chunks.created"


def test_create_knowledge_chunks_returns_existing_chunks_for_same_content() -> None:
    source = KnowledgeSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_file_artifact_id=uuid.uuid4(),
        converted_markdown_artifact_id=uuid.uuid4(),
        title="Teacher Notes",
        access_scope="public_safe",
        conversion_status="converted",
        status="active",
        metadata_payload={},
    )
    content = "# Notes\n\nInclude threshold equality."
    draft = build_markdown_chunk_drafts(content)[0]
    existing = KnowledgeChunk(
        id=uuid.uuid4(),
        organization_id=source.organization_id,
        knowledge_source_id=source.id,
        converted_markdown_artifact_id=source.converted_markdown_artifact_id,
        position=draft.position,
        chunk_key=draft.chunk_key,
        heading_path=draft.heading_path,
        content=draft.content,
        content_hash=draft.content_hash,
        character_count=draft.character_count,
        status="active",
        metadata_payload={},
    )
    session = RecordingSession()
    session.scalars_results = [existing]

    chunks = create_knowledge_chunks(
        session,  # type: ignore[arg-type]
        knowledge_source=source,
        markdown_content=content,
    )

    assert chunks == [existing]
    assert records(session, KnowledgeChunk) == []
    assert records(session, AuditEvent) == []


def test_create_knowledge_chunks_requires_explicit_replace_for_changed_content() -> None:
    source = KnowledgeSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        source_file_artifact_id=uuid.uuid4(),
        converted_markdown_artifact_id=uuid.uuid4(),
        title="Teacher Notes",
        access_scope="public_safe",
        conversion_status="converted",
        status="active",
        metadata_payload={},
    )
    existing = KnowledgeChunk(
        id=uuid.uuid4(),
        organization_id=source.organization_id,
        knowledge_source_id=source.id,
        converted_markdown_artifact_id=source.converted_markdown_artifact_id,
        position=0,
        chunk_key="chunk-0000",
        heading_path=["Notes"],
        content="old",
        content_hash="old-hash",
        character_count=3,
        status="active",
        metadata_payload={},
    )
    session = RecordingSession()
    session.scalars_results = [existing]

    with pytest.raises(KnowledgeLibraryError, match="replace_existing"):
        create_knowledge_chunks(
            session,  # type: ignore[arg-type]
            knowledge_source=source,
            markdown_content="# Notes\n\nNew content.",
        )

    chunks = create_knowledge_chunks(
        session,  # type: ignore[arg-type]
        knowledge_source=source,
        markdown_content="# Notes\n\nNew content.",
        replace_existing=True,
    )

    assert existing.status == "superseded"
    assert len(chunks) == 1
    assert chunks[0].content_hash != "old-hash"
