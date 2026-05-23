import uuid

import pytest
from sqlalchemy import CheckConstraint

from app.db.models import ArtifactConversion, AuditEvent, FilePurpose, KnowledgeChunk, KnowledgeSource, RubricSuggestion
from app.db.services.knowledge_library import (
    KnowledgeLibraryError,
    build_markdown_chunk_drafts,
    citation_for_chunk,
    convert_knowledge_source_to_markdown,
    create_knowledge_chunks,
    create_knowledge_source_version,
    normalize_access_scope,
    register_knowledge_source,
    revise_knowledge_source,
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


def test_invalid_access_scope_is_rejected_instead_of_widened() -> None:
    assert normalize_access_scope("public-safe") == "public_safe"
    with pytest.raises(KnowledgeLibraryError, match="Invalid knowledge access scope"):
        normalize_access_scope("public")

    session = RecordingSession(scalar_results=[file_purpose("knowledge_source")])
    with pytest.raises(KnowledgeLibraryError, match="Invalid knowledge access scope"):
        register_knowledge_source(
            session,  # type: ignore[arg-type]
            organization_id=uuid.uuid4(),
            title="Private Notes",
            source_filename="notes.md",
            source_storage_uri="fixture://notes.md",
            access_scope="schoolwide",
        )


def test_create_knowledge_source_version_preserves_previous_source_and_audits() -> None:
    organization_id = uuid.uuid4()
    previous_source = KnowledgeSource(
        id=uuid.uuid4(),
        organization_id=organization_id,
        owner_user_id=uuid.uuid4(),
        subject_pack_id=uuid.uuid4(),
        source_file_artifact_id=uuid.uuid4(),
        converted_markdown_artifact_id=uuid.uuid4(),
        title="Teacher Notes",
        version_number=1,
        access_scope="public_safe",
        conversion_status="converted",
        status="active",
        summary="Original guidance.",
        metadata_payload={"source_format": "markdown"},
    )
    previous_state = {
        "source_file_artifact_id": previous_source.source_file_artifact_id,
        "converted_markdown_artifact_id": previous_source.converted_markdown_artifact_id,
        "conversion_status": previous_source.conversion_status,
        "status": previous_source.status,
    }
    session = RecordingSession(scalar_results=[file_purpose("knowledge_source")])

    version = create_knowledge_source_version(
        session,  # type: ignore[arg-type]
        previous_source=previous_source,
        source_filename="teacher_notes_v2.md",
        source_storage_uri="fixture://teacher_notes_v2.md",
        actor_user_id=previous_source.owner_user_id,
        reason="Teacher uploaded revised guidance.",
    )

    source_artifacts = [record for record in session.added if record.__class__.__name__ == "FileArtifact"]
    audit = records(session, AuditEvent)[0]

    assert version.id != previous_source.id
    assert version.source_file_artifact_id == source_artifacts[0].id
    assert version.version_number == 2
    assert version.conversion_status == "pending"
    assert version.status == "draft"
    assert version.metadata_payload["previous_knowledge_source_id"] == str(previous_source.id)
    assert version.metadata_payload["previous_source_file_artifact_id"] == str(previous_source.source_file_artifact_id)
    assert previous_source.source_file_artifact_id == previous_state["source_file_artifact_id"]
    assert previous_source.converted_markdown_artifact_id == previous_state["converted_markdown_artifact_id"]
    assert previous_source.conversion_status == previous_state["conversion_status"]
    assert previous_source.status == previous_state["status"]
    assert audit.action == "knowledge_source.version_created"
    assert audit.previous_state["knowledge_source_id"] == str(previous_source.id)
    assert audit.new_state["previous_knowledge_source_id"] == str(previous_source.id)


def test_revise_knowledge_source_creates_converts_and_chunks_new_version() -> None:
    organization_id = uuid.uuid4()
    previous_source = KnowledgeSource(
        id=uuid.uuid4(),
        organization_id=organization_id,
        owner_user_id=uuid.uuid4(),
        source_file_artifact_id=uuid.uuid4(),
        converted_markdown_artifact_id=uuid.uuid4(),
        title="Teacher Notes",
        version_number=1,
        access_scope="public_safe",
        conversion_status="converted",
        status="active",
        metadata_payload={"source_format": "markdown"},
    )
    session = RecordingSession(
        scalar_results=[
            file_purpose("knowledge_source"),
            file_purpose("converted_markdown"),
        ]
    )

    result = revise_knowledge_source(
        session,  # type: ignore[arg-type]
        previous_source=previous_source,
        source_filename="teacher_notes_v2.md",
        source_storage_uri="fixture://teacher_notes_v2.md",
        source_content="# Revised Notes\n\nInclude threshold equality.",
        actor_user_id=previous_source.owner_user_id,
        reason="Teacher uploaded revised guidance.",
    )

    assert result.knowledge_source.id != previous_source.id
    assert result.knowledge_source.version_number == 2
    assert result.knowledge_source.conversion_status == "converted"
    assert result.knowledge_source.status == "active"
    assert result.converted_markdown_artifact is not None
    assert len(result.chunks) == 1
    assert result.chunks[0].knowledge_source_id == result.knowledge_source.id
    assert result.chunks[0].metadata_payload["knowledge_source_version_number"] == 2
    assert previous_source.conversion_status == "converted"
    assert previous_source.status == "active"
    assert [event.action for event in records(session, AuditEvent)] == [
        "knowledge_source.version_created",
        "knowledge_source.converted",
        "knowledge_chunks.created",
    ]


def test_revise_knowledge_source_stops_safely_for_unsupported_revision() -> None:
    previous_source = KnowledgeSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        source_file_artifact_id=uuid.uuid4(),
        converted_markdown_artifact_id=uuid.uuid4(),
        title="Teacher Notes",
        version_number=1,
        access_scope="organization",
        conversion_status="converted",
        status="active",
        metadata_payload={"source_format": "markdown"},
    )
    session = RecordingSession(scalar_results=[file_purpose("knowledge_source")])

    result = revise_knowledge_source(
        session,  # type: ignore[arg-type]
        previous_source=previous_source,
        source_filename="teacher_notes_v2.pdf",
        source_storage_uri="fixture://teacher_notes_v2.pdf",
        source_content="ignored",
        actor_user_id=previous_source.owner_user_id,
        reason="Teacher uploaded revised PDF guidance.",
    )

    assert result.knowledge_source.version_number == 2
    assert result.knowledge_source.conversion_status == "unsupported"
    assert result.knowledge_source.status == "draft"
    assert result.converted_markdown_artifact is None
    assert result.chunks == []
    assert previous_source.conversion_status == "converted"
    assert previous_source.status == "active"
    assert [event.action for event in records(session, AuditEvent)] == [
        "knowledge_source.version_created",
        "knowledge_source.conversion_unsupported",
    ]


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
    assert chunks[0].metadata_payload["knowledge_source_title"] == "Teacher Notes"
    assert chunks[0].metadata_payload["knowledge_source_version_number"] == 1
    assert chunks[0].metadata_payload["access_scope"] == "public_safe"
    citation = citation_for_chunk(chunks[0])
    assert citation["knowledge_source_title"] == "Teacher Notes"
    assert citation["knowledge_source_version_number"] == 1
    assert citation["access_scope"] == "public_safe"
    assert citation["excerpt"] == "# Notes Include equality at the passing threshold."
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


def test_create_knowledge_chunks_blocks_replacement_when_existing_chunk_is_cited() -> None:
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
    session = RecordingSession(scalar_results=[uuid.uuid4()])
    session.scalars_results = [existing]

    with pytest.raises(KnowledgeLibraryError, match="create a new source version"):
        create_knowledge_chunks(
            session,  # type: ignore[arg-type]
            knowledge_source=source,
            markdown_content="# Notes\n\nNew content.",
            replace_existing=True,
        )

    assert existing.status == "active"
