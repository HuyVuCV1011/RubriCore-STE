import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ArtifactConversion, FileArtifact, FilePurpose, KnowledgeSource


VALID_ACCESS_SCOPES = {"private", "course", "organization", "subject_pack", "public_safe"}


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
