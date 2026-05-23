from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ArtifactConversion, AuditEvent, FileArtifact, FilePurpose, KnowledgeChunk, KnowledgeSource


VALID_ACCESS_SCOPES = {"private", "course", "organization", "subject_pack", "public_safe"}
SUPPORTED_MARKDOWN_FORMATS = {"markdown"}
SUPPORTED_TEXT_FORMATS = {"text"}


class KnowledgeLibraryError(ValueError):
    """Raised when a knowledge-library operation violates lifecycle rules."""


@dataclass(frozen=True)
class MarkdownChunkDraft:
    position: int
    chunk_key: str
    heading_path: list[str]
    content: str
    content_hash: str
    character_count: int
    metadata_payload: dict[str, Any]


@dataclass(frozen=True)
class RetrievedKnowledgeChunk:
    chunk: KnowledgeChunk
    score: int
    matched_terms: list[str]
    citation: dict[str, Any]


def _get_file_purpose(db: Session, organization_id: uuid.UUID, key: str) -> FilePurpose:
    purpose = db.scalar(
        select(FilePurpose).where(
            FilePurpose.organization_id == organization_id,
            FilePurpose.key == key,
        )
    )
    if purpose is None:
        raise ValueError(f"Missing file purpose: {key}")
    return purpose


def normalize_access_scope(access_scope: str | None) -> str:
    if access_scope is None:
        return "organization"
    normalized = access_scope.replace("-", "_")
    return normalized if normalized in VALID_ACCESS_SCOPES else "organization"


def _source_format_from_filename(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "md": "markdown",
        "markdown": "markdown",
        "txt": "text",
        "rtf": "rtf",
        "pdf": "pdf",
        "doc": "doc",
        "docx": "docx",
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "sql": "sql",
        "ipynb": "notebook",
        "csv": "csv",
        "tsv": "tsv",
        "xlsx": "xlsx",
        "json": "json",
        "xml": "xml",
        "zip": "archive",
    }.get(extension, "unknown")


def register_knowledge_source(
    db: Session,
    *,
    organization_id: uuid.UUID,
    title: str,
    source_filename: str,
    source_storage_uri: str,
    owner_user_id: uuid.UUID | None = None,
    subject_pack_id: uuid.UUID | None = None,
    access_scope: str | None = "organization",
    source_type: str = "knowledge_library",
    summary: str | None = None,
    metadata_payload: dict[str, Any] | None = None,
    actor_source: str = "teacher",
    reason: str | None = None,
    request_id: str | None = None,
) -> KnowledgeSource:
    """Register a knowledge source artifact before conversion or chunking."""

    scope = normalize_access_scope(access_scope)
    source_format = _source_format_from_filename(source_filename)
    metadata = metadata_payload or {}
    source_purpose = _get_file_purpose(db, organization_id, "knowledge_source")
    supported_formats = SUPPORTED_MARKDOWN_FORMATS | SUPPORTED_TEXT_FORMATS
    parser_status = "supported" if source_format in supported_formats else "unsupported"
    document_formats = {"markdown", "text", "pdf", "doc", "docx", "rtf"}

    source_artifact = FileArtifact(
        organization_id=organization_id,
        file_purpose_id=source_purpose.id,
        original_filename=source_filename,
        normalized_filename=source_filename,
        file_extension=source_filename.rsplit(".", 1)[-1] if "." in source_filename else None,
        mime_type=_mime_type_for_source_format(source_format),
        detected_file_category="document" if source_format in document_formats else None,
        storage_uri=source_storage_uri,
        import_source=source_type,
        owner_user_id=owner_user_id,
        uploaded_by_user_id=owner_user_id,
        source_type=source_type,
        source_format=source_format,
        access_scope=scope,
        parser_support_status=parser_status,
        status="active",
        metadata_payload=metadata,
    )
    db.add(source_artifact)
    db.flush()

    knowledge_source = KnowledgeSource(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        subject_pack_id=subject_pack_id,
        source_file_artifact_id=source_artifact.id,
        title=title,
        version_number=1,
        access_scope=scope,
        conversion_status="pending" if parser_status == "supported" else "unsupported",
        status="draft",
        summary=summary,
        metadata_payload={"source_format": source_format, **metadata},
    )
    db.add(knowledge_source)
    db.flush()

    _audit_knowledge_event(
        db,
        organization_id=organization_id,
        actor_user_id=owner_user_id,
        actor_source=actor_source,
        action="knowledge_source.registered",
        entity_type="knowledge_source",
        entity_id=knowledge_source.id,
        previous_state={},
        new_state={
            "knowledge_source_id": str(knowledge_source.id),
            "source_file_artifact_id": str(source_artifact.id),
            "title": title,
            "access_scope": scope,
            "source_format": source_format,
            "conversion_status": knowledge_source.conversion_status,
            "status": knowledge_source.status,
        },
        reason=reason,
        request_id=request_id,
    )
    return knowledge_source


def convert_knowledge_source_to_markdown(
    db: Session,
    *,
    knowledge_source: KnowledgeSource,
    source_filename: str,
    source_content: str | None,
    markdown_filename: str | None = None,
    markdown_storage_uri: str | None = None,
    converter_version: str = "1.0",
    actor_user_id: uuid.UUID | None = None,
    actor_source: str = "system",
    reason: str | None = None,
    request_id: str | None = None,
) -> FileArtifact | None:
    """Convert supported local source content to a derived Markdown artifact."""

    source_format = str(
        knowledge_source.metadata_payload.get("source_format") or _source_format_from_filename(source_filename)
    )
    scope = normalize_access_scope(knowledge_source.access_scope)

    if source_format not in SUPPORTED_MARKDOWN_FORMATS | SUPPORTED_TEXT_FORMATS:
        _record_conversion_without_output(
            db,
            knowledge_source=knowledge_source,
            conversion_status="unsupported",
            converter_name="unsupported_local_converter",
            converter_version=converter_version,
            error_message=f"No local Markdown converter for source format {source_format!r}.",
            actor_user_id=actor_user_id,
            actor_source=actor_source,
            reason=reason,
            request_id=request_id,
        )
        return None

    if source_content is None:
        _record_conversion_without_output(
            db,
            knowledge_source=knowledge_source,
            conversion_status="failed",
            converter_name="local_markdown_converter",
            converter_version=converter_version,
            error_message="Source content is required for local conversion.",
            actor_user_id=actor_user_id,
            actor_source=actor_source,
            reason=reason,
            request_id=request_id,
        )
        return None

    converter_name = "markdown_passthrough" if source_format == "markdown" else "plain_text_to_markdown"
    if source_format == "markdown":
        markdown_content = source_content
    else:
        markdown_content = convert_plain_text_to_markdown(source_content, title=knowledge_source.title)
    markdown_purpose = _get_file_purpose(db, knowledge_source.organization_id, "converted_markdown")
    output_filename = markdown_filename or _markdown_filename_for(source_filename)

    markdown_artifact = FileArtifact(
        organization_id=knowledge_source.organization_id,
        file_purpose_id=markdown_purpose.id,
        original_filename=output_filename,
        normalized_filename=output_filename,
        file_extension="md",
        mime_type="text/markdown",
        detected_file_category="document",
        storage_uri=markdown_storage_uri or f"derived://knowledge/{knowledge_source.id}/{output_filename}",
        import_source="knowledge_library_conversion",
        owner_user_id=knowledge_source.owner_user_id,
        uploaded_by_user_id=actor_user_id or knowledge_source.owner_user_id,
        source_type="system_conversion",
        source_format="markdown",
        access_scope=scope,
        parser_support_status="supported",
        status="active",
        metadata_payload={
            "source_file_artifact_id": str(knowledge_source.source_file_artifact_id),
            "knowledge_source_id": str(knowledge_source.id),
            "content_sha256": _hash_text(markdown_content),
        },
    )
    db.add(markdown_artifact)
    db.flush()

    db.add(
        ArtifactConversion(
            organization_id=knowledge_source.organization_id,
            source_file_artifact_id=knowledge_source.source_file_artifact_id,
            converted_file_artifact_id=markdown_artifact.id,
            conversion_type="markdown",
            conversion_status="completed",
            converter_name=converter_name,
            converter_version=converter_version,
            conversion_schema_version="1.0",
            access_scope=scope,
            warnings={},
            metadata_payload={
                "knowledge_source_id": str(knowledge_source.id),
                "source_format": source_format,
                "markdown_character_count": len(markdown_content),
            },
        )
    )

    previous_state = {
        "conversion_status": knowledge_source.conversion_status,
        "status": knowledge_source.status,
        "converted_markdown_artifact_id": (
            str(knowledge_source.converted_markdown_artifact_id)
            if knowledge_source.converted_markdown_artifact_id is not None
            else None
        ),
    }
    knowledge_source.converted_markdown_artifact_id = markdown_artifact.id
    knowledge_source.conversion_status = "converted"
    knowledge_source.status = "active"
    db.flush()

    _audit_knowledge_event(
        db,
        organization_id=knowledge_source.organization_id,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action="knowledge_source.converted",
        entity_type="knowledge_source",
        entity_id=knowledge_source.id,
        previous_state=previous_state,
        new_state={
            "conversion_status": knowledge_source.conversion_status,
            "status": knowledge_source.status,
            "converted_markdown_artifact_id": str(markdown_artifact.id),
            "converter_name": converter_name,
        },
        reason=reason,
        request_id=request_id,
    )
    return markdown_artifact


def convert_plain_text_to_markdown(content: str, *, title: str) -> str:
    stripped = content.strip()
    if not stripped:
        return f"# {title}\n"
    if stripped.startswith("#"):
        return stripped + "\n"
    return f"# {title}\n\n{stripped}\n"


def build_markdown_chunk_drafts(markdown_content: str, *, max_characters: int = 1200) -> list[MarkdownChunkDraft]:
    sections = _split_markdown_sections(markdown_content)
    drafts: list[MarkdownChunkDraft] = []
    for heading_path, content in sections:
        for part in _split_long_section(content, max_characters=max_characters):
            normalized = part.strip()
            if not normalized:
                continue
            position = len(drafts)
            content_hash = _hash_text(normalized)
            drafts.append(
                MarkdownChunkDraft(
                    position=position,
                    chunk_key=f"chunk-{position:04d}",
                    heading_path=heading_path,
                    content=normalized,
                    content_hash=content_hash,
                    character_count=len(normalized),
                    metadata_payload={"chunker": "markdown_heading_v1"},
                )
            )
    return drafts


def create_knowledge_chunks(
    db: Session,
    *,
    knowledge_source: KnowledgeSource,
    markdown_content: str,
    max_characters: int = 1200,
    replace_existing: bool = False,
    actor_user_id: uuid.UUID | None = None,
    actor_source: str = "system",
    reason: str | None = None,
    request_id: str | None = None,
) -> list[KnowledgeChunk]:
    if knowledge_source.conversion_status != "converted" or knowledge_source.converted_markdown_artifact_id is None:
        raise KnowledgeLibraryError("Knowledge source must have converted Markdown before chunking.")

    drafts = build_markdown_chunk_drafts(markdown_content, max_characters=max_characters)
    existing_chunks = list(
        db.scalars(
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.knowledge_source_id == knowledge_source.id,
                KnowledgeChunk.status == "active",
            )
            .order_by(KnowledgeChunk.position)
        )
    )
    if existing_chunks:
        existing_hashes = [chunk.content_hash for chunk in existing_chunks]
        draft_hashes = [draft.content_hash for draft in drafts]
        if existing_hashes == draft_hashes:
            return existing_chunks
        if not replace_existing:
            raise KnowledgeLibraryError(
                "Knowledge source already has active chunks with different content; use replace_existing=True."
            )
        for chunk in existing_chunks:
            chunk.status = "superseded"
        db.flush()

    chunks: list[KnowledgeChunk] = []
    for draft in drafts:
        chunk = KnowledgeChunk(
            organization_id=knowledge_source.organization_id,
            knowledge_source_id=knowledge_source.id,
            converted_markdown_artifact_id=knowledge_source.converted_markdown_artifact_id,
            position=draft.position,
            chunk_key=draft.chunk_key,
            heading_path=draft.heading_path,
            content=draft.content,
            content_hash=draft.content_hash,
            character_count=draft.character_count,
            status="active",
            metadata_payload=draft.metadata_payload,
        )
        db.add(chunk)
        chunks.append(chunk)

    db.flush()
    _audit_knowledge_event(
        db,
        organization_id=knowledge_source.organization_id,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action="knowledge_chunks.created",
        entity_type="knowledge_source",
        entity_id=knowledge_source.id,
        previous_state={},
        new_state={
            "knowledge_source_id": str(knowledge_source.id),
            "chunk_count": len(chunks),
            "chunk_ids": [str(chunk.id) for chunk in chunks],
            "replaced_chunk_ids": [str(chunk.id) for chunk in existing_chunks] if replace_existing else [],
        },
        reason=reason,
        request_id=request_id,
    )
    return chunks


def retrieve_candidate_chunks(
    db: Session,
    *,
    organization_id: uuid.UUID,
    query: str,
    allowed_access_scopes: set[str],
    source_ids: set[uuid.UUID] | None = None,
    limit: int = 10,
) -> list[RetrievedKnowledgeChunk]:
    terms = _query_terms(query)
    if not terms:
        return []

    statement = (
        select(KnowledgeChunk)
        .join(KnowledgeSource, KnowledgeChunk.knowledge_source_id == KnowledgeSource.id)
        .where(
            KnowledgeChunk.organization_id == organization_id,
            KnowledgeChunk.status == "active",
            KnowledgeSource.status == "active",
            KnowledgeSource.access_scope.in_({normalize_access_scope(scope) for scope in allowed_access_scopes}),
        )
        .order_by(KnowledgeChunk.position)
    )
    if source_ids is not None:
        statement = statement.where(KnowledgeChunk.knowledge_source_id.in_(source_ids))

    chunks = list(db.scalars(statement))
    ranked: list[RetrievedKnowledgeChunk] = []
    for chunk in chunks:
        content_lower = chunk.content.lower()
        heading_text = " ".join(str(item) for item in chunk.heading_path).lower()
        matched_terms = [term for term in terms if term in content_lower or term in heading_text]
        if not matched_terms:
            continue
        score = len(matched_terms) + sum(1 for term in matched_terms if term in heading_text)
        ranked.append(
            RetrievedKnowledgeChunk(
                chunk=chunk,
                score=score,
                matched_terms=matched_terms,
                citation=citation_for_chunk(chunk),
            )
        )

    return sorted(ranked, key=lambda item: (-item.score, item.chunk.position))[:limit]


def citation_for_chunk(chunk: KnowledgeChunk) -> dict[str, Any]:
    return {
        "knowledge_source_id": str(chunk.knowledge_source_id),
        "chunk_id": str(chunk.id),
        "chunk_key": chunk.chunk_key,
        "heading_path": list(chunk.heading_path),
        "content_hash": chunk.content_hash,
    }


def register_markdown_knowledge_source(
    db: Session,
    *,
    organization_id: uuid.UUID,
    title: str,
    source_filename: str,
    source_storage_uri: str,
    markdown_filename: str,
    markdown_storage_uri: str,
    owner_user_id: uuid.UUID | None = None,
    subject_pack_id: uuid.UUID | None = None,
    access_scope: str | None = "organization",
    summary: str | None = None,
    metadata_payload: dict | None = None,
) -> KnowledgeSource:
    """Register an already-converted Markdown knowledge source.

    This helper records artifact metadata and conversion provenance only. It does
    not perform file upload, Markdown conversion, chunking, retrieval indexing,
    rubric suggestions, or access enforcement.
    """

    scope = normalize_access_scope(access_scope)
    source_purpose = _get_file_purpose(db, organization_id, "knowledge_source")
    markdown_purpose = _get_file_purpose(db, organization_id, "converted_markdown")
    metadata = metadata_payload or {}

    source_artifact = FileArtifact(
        organization_id=organization_id,
        file_purpose_id=source_purpose.id,
        original_filename=source_filename,
        normalized_filename=source_filename,
        file_extension=source_filename.rsplit(".", 1)[-1] if "." in source_filename else None,
        mime_type="text/markdown",
        detected_file_category="document",
        storage_uri=source_storage_uri,
        import_source="knowledge_library",
        owner_user_id=owner_user_id,
        uploaded_by_user_id=owner_user_id,
        source_type="knowledge_library",
        source_format=_source_format_from_filename(source_filename),
        access_scope=scope,
        parser_support_status="supported",
        status="active",
        metadata_payload=metadata,
    )
    db.add(source_artifact)
    db.flush()

    markdown_artifact = FileArtifact(
        organization_id=organization_id,
        file_purpose_id=markdown_purpose.id,
        original_filename=markdown_filename,
        normalized_filename=markdown_filename,
        file_extension="md",
        mime_type="text/markdown",
        detected_file_category="document",
        storage_uri=markdown_storage_uri,
        import_source="knowledge_library_conversion",
        owner_user_id=owner_user_id,
        uploaded_by_user_id=owner_user_id,
        source_type="system_conversion",
        source_format="markdown",
        access_scope=scope,
        parser_support_status="supported",
        status="active",
        metadata_payload={"source_file_artifact_id": str(source_artifact.id), **metadata},
    )
    db.add(markdown_artifact)
    db.flush()

    db.add(
        ArtifactConversion(
            organization_id=organization_id,
            source_file_artifact_id=source_artifact.id,
            converted_file_artifact_id=markdown_artifact.id,
            conversion_type="markdown",
            conversion_status="completed",
            converter_name="preconverted_markdown",
            converter_version="1.0",
            conversion_schema_version="1.0",
            access_scope=scope,
            warnings={},
            metadata_payload=metadata,
        )
    )

    knowledge_source = KnowledgeSource(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        subject_pack_id=subject_pack_id,
        source_file_artifact_id=source_artifact.id,
        converted_markdown_artifact_id=markdown_artifact.id,
        title=title,
        version_number=1,
        access_scope=scope,
        conversion_status="converted",
        status="active",
        summary=summary,
        metadata_payload=metadata,
    )
    db.add(knowledge_source)
    return knowledge_source


def _record_conversion_without_output(
    db: Session,
    *,
    knowledge_source: KnowledgeSource,
    conversion_status: str,
    converter_name: str,
    converter_version: str,
    error_message: str,
    actor_user_id: uuid.UUID | None,
    actor_source: str,
    reason: str | None,
    request_id: str | None,
) -> None:
    scope = normalize_access_scope(knowledge_source.access_scope)
    db.add(
        ArtifactConversion(
            organization_id=knowledge_source.organization_id,
            source_file_artifact_id=knowledge_source.source_file_artifact_id,
            conversion_type="markdown",
            conversion_status=conversion_status,
            converter_name=converter_name,
            converter_version=converter_version,
            conversion_schema_version="1.0",
            access_scope=scope,
            warnings={},
            error_message=error_message,
            metadata_payload={"knowledge_source_id": str(knowledge_source.id)},
        )
    )
    previous_state = {
        "conversion_status": knowledge_source.conversion_status,
        "status": knowledge_source.status,
    }
    knowledge_source.conversion_status = conversion_status
    knowledge_source.status = "draft"
    db.flush()
    _audit_knowledge_event(
        db,
        organization_id=knowledge_source.organization_id,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action=(
            "knowledge_source.conversion_unsupported"
            if conversion_status == "unsupported"
            else "knowledge_source.conversion_failed"
        ),
        entity_type="knowledge_source",
        entity_id=knowledge_source.id,
        previous_state=previous_state,
        new_state={
            "conversion_status": knowledge_source.conversion_status,
            "status": knowledge_source.status,
            "error_message": error_message,
        },
        reason=reason,
        request_id=request_id,
    )


def _mime_type_for_source_format(source_format: str) -> str | None:
    return {
        "markdown": "text/markdown",
        "text": "text/plain",
        "json": "application/json",
        "xml": "application/xml",
        "pdf": "application/pdf",
        "csv": "text/csv",
        "tsv": "text/tab-separated-values",
    }.get(source_format)


def _markdown_filename_for(source_filename: str) -> str:
    base = source_filename.rsplit(".", 1)[0] if "." in source_filename else source_filename
    return f"{base}.md"


def _hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _split_markdown_sections(markdown_content: str) -> list[tuple[list[str], str]]:
    lines = markdown_content.splitlines()
    sections: list[tuple[list[str], list[str]]] = []
    current_heading_path: list[str] = []
    current_lines: list[str] = []
    heading_stack: list[tuple[int, str]] = []

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            if current_lines:
                sections.append((current_heading_path, current_lines))
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            heading_stack = [
                (item_level, item_heading) for item_level, item_heading in heading_stack if item_level < level
            ]
            heading_stack.append((level, heading))
            current_heading_path = [item_heading for _, item_heading in heading_stack]
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading_path, current_lines))

    return [(heading_path, "\n".join(content_lines).strip()) for heading_path, content_lines in sections]


def _split_long_section(content: str, *, max_characters: int) -> list[str]:
    if len(content) <= max_characters:
        return [content]

    parts: list[str] = []
    current: list[str] = []
    current_length = 0
    in_code_fence = False

    for paragraph in content.split("\n\n"):
        if paragraph.strip().startswith("```"):
            in_code_fence = not in_code_fence
        projected_length = current_length + len(paragraph) + 2
        if current and projected_length > max_characters and not in_code_fence:
            parts.append("\n\n".join(current))
            current = [paragraph]
            current_length = len(paragraph)
        else:
            current.append(paragraph)
            current_length = projected_length

    if current:
        parts.append("\n\n".join(current))
    return parts


def _query_terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9_]+", query.lower()) if len(term) > 2]


def _audit_knowledge_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    actor_source: str,
    previous_state: dict[str, Any],
    new_state: dict[str, Any],
    reason: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        actor_source=actor_source,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=request_id,
        previous_state=previous_state,
        new_state=new_state,
        reason=reason,
    )
    db.add(event)
    return event
