import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


ARTIFACT_SOURCE_TYPE_CHECK = (
    "source_type in ("
    "'unknown', 'web_upload', 'fixture_import', 'teacher_import', "
    "'api_import', 'batch_import', 'system_conversion', 'knowledge_library'"
    ")"
)

ARTIFACT_SOURCE_FORMAT_CHECK = (
    "source_format in ("
    "'unknown', 'text', 'markdown', 'python', 'javascript', 'typescript', "
    "'sql', 'notebook', 'pdf', 'doc', 'docx', 'rtf', 'csv', 'tsv', 'xlsx', "
    "'json', 'xml', 'image', 'audio', 'video', 'archive'"
    ")"
)


class FileArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "file_artifacts"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    file_purpose_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_purposes.id"), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_extension: Mapped[str | None] = mapped_column(String(40))
    mime_type: Mapped[str | None] = mapped_column(String(255))
    detected_file_category: Mapped[str | None] = mapped_column(String(80))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    storage_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    import_source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    source_format: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    access_scope: Mapped[str] = mapped_column(String(40), nullable=False, default="organization")
    parser_support_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "access_scope in ('private', 'course', 'organization', 'subject_pack', 'public_safe')",
            name="file_artifact_access_scope",
        ),
        CheckConstraint(ARTIFACT_SOURCE_TYPE_CHECK, name="file_artifact_source_type"),
        CheckConstraint(ARTIFACT_SOURCE_FORMAT_CHECK, name="file_artifact_source_format"),
        CheckConstraint(
            "parser_support_status in ('unknown', 'supported', 'unsupported', 'failed')",
            name="file_artifact_parser_support_status",
        ),
        CheckConstraint(
            "status in ('active', 'archived', 'deleted')",
            name="file_artifact_status",
        ),
        CheckConstraint(
            "file_size_bytes is null or file_size_bytes >= 0",
            name="file_artifact_size_nonnegative",
        ),
        Index("ix_file_artifacts_organization_status", "organization_id", "status"),
        Index("ix_file_artifacts_organization_scope", "organization_id", "access_scope"),
        Index("ix_file_artifacts_owner", "owner_user_id"),
        Index("ix_file_artifacts_uploaded_by", "uploaded_by_user_id"),
        Index("ix_file_artifacts_source_type", "source_type"),
        Index("ix_file_artifacts_uploaded_at", "uploaded_at"),
        Index("ix_file_artifacts_purpose", "file_purpose_id"),
        Index("ix_file_artifacts_organization_purpose", "organization_id", "file_purpose_id"),
        Index("ix_file_artifacts_checksum", "checksum_sha256"),
    )


class ArtifactConversion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "artifact_conversions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    source_file_artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("file_artifacts.id"),
        nullable=False,
    )
    converted_file_artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("file_artifacts.id"))
    conversion_type: Mapped[str] = mapped_column(String(80), nullable=False, default="markdown")
    conversion_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    converter_name: Mapped[str | None] = mapped_column(String(160))
    converter_version: Mapped[str | None] = mapped_column(String(80))
    conversion_schema_version: Mapped[str] = mapped_column(String(80), nullable=False, default="1.0")
    access_scope: Mapped[str] = mapped_column(String(40), nullable=False, default="organization")
    warnings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "conversion_type in ('markdown', 'text', 'preview', 'metadata')",
            name="artifact_conversion_type",
        ),
        CheckConstraint(
            "conversion_status in ('pending', 'running', 'completed', 'unsupported', 'failed')",
            name="artifact_conversion_status",
        ),
        CheckConstraint(
            "access_scope in ('private', 'course', 'organization', 'subject_pack', 'public_safe')",
            name="artifact_conversion_access_scope",
        ),
        Index("ix_artifact_conversions_organization_status", "organization_id", "conversion_status"),
        Index("ix_artifact_conversions_source", "source_file_artifact_id"),
        Index("ix_artifact_conversions_converted", "converted_file_artifact_id"),
        Index(
            "ix_artifact_conversions_source_type",
            "source_file_artifact_id",
            "conversion_type",
        ),
    )


class EvidenceExtraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_extractions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    file_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_artifacts.id"), nullable=False)
    output_file_artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("file_artifacts.id"))
    extraction_type: Mapped[str] = mapped_column(String(80), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    parser_name: Mapped[str | None] = mapped_column(String(160))
    parser_version: Mapped[str | None] = mapped_column(String(80))
    extraction_schema_version: Mapped[str] = mapped_column(String(80), nullable=False, default="1.0")
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    warnings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "extraction_status in ('pending', 'running', 'completed', 'unsupported', 'failed')",
            name="evidence_extraction_status",
        ),
        Index("ix_evidence_extractions_organization", "organization_id"),
        Index("ix_evidence_extractions_file_artifact", "file_artifact_id"),
        Index(
            "ix_evidence_extractions_artifact_status",
            "file_artifact_id",
            "extraction_status",
        ),
        Index("ix_evidence_extractions_status", "extraction_status"),
    )


class AssessmentMaterial(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessment_materials"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessments.id"))
    assessment_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessment_items.id"))
    file_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_artifacts.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "assessment_id is not null or assessment_item_id is not null",
            name="assessment_material_has_context",
        ),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="assessment_material_status",
        ),
        Index("ix_assessment_materials_assessment", "assessment_id"),
        Index("ix_assessment_materials_assessment_item", "assessment_item_id"),
        Index("ix_assessment_materials_file_artifact", "file_artifact_id"),
    )


class AnswerKeyMaterial(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "answer_key_materials"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    answer_key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("answer_keys.id"))
    answer_key_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("answer_key_versions.id"))
    file_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_artifacts.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    metadata_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "answer_key_id is not null or answer_key_version_id is not null",
            name="answer_key_material_has_context",
        ),
        CheckConstraint(
            "status in ('active', 'archived')",
            name="answer_key_material_status",
        ),
        Index("ix_answer_key_materials_answer_key", "answer_key_id"),
        Index("ix_answer_key_materials_answer_key_version", "answer_key_version_id"),
        Index("ix_answer_key_materials_file_artifact", "file_artifact_id"),
    )
