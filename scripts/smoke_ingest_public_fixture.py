import hashlib
import json
import mimetypes
import sys
from pathlib import Path

from sqlalchemy import func, select


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import FileArtifact, FilePurpose, Organization  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


FIXTURE_ROOT = Path("tests/fixtures/public/python_score_summary")
PURPOSE_MAP = {
    "assessment_material": "assessment_material",
    "answer_key_source": "answer_key_source",
    "submission_evidence": "submission_evidence",
    "reference_solution": "reference_solution",
    "extracted_representation": "extracted_representation",
    "rubric_source": "rubric_source",
    "knowledge_source": "knowledge_source",
    "converted_markdown": "converted_markdown",
}


def load_manifest() -> dict:
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def detect_category(path: Path) -> str:
    if path.suffix in {".py", ".sql", ".js", ".ts"}:
        return "code"
    if path.suffix in {".md", ".markdown", ".txt", ".rtf", ".pdf", ".doc", ".docx"}:
        return "document"
    if path.suffix in {".csv", ".tsv", ".xlsx", ".json", ".xml"}:
        return "data"
    return "unknown"


def detect_source_format(path: Path) -> str:
    return {
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "text",
        ".rtf": "rtf",
        ".pdf": "pdf",
        ".doc": "doc",
        ".docx": "docx",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".sql": "sql",
        ".ipynb": "notebook",
        ".csv": "csv",
        ".tsv": "tsv",
        ".xlsx": "xlsx",
        ".json": "json",
        ".xml": "xml",
        ".zip": "archive",
    }.get(path.suffix.lower(), "unknown")


def normalize_access_scope(value: str | None) -> str:
    if value is None:
        return "organization"
    normalized = value.replace("-", "_")
    allowed = {"private", "course", "organization", "subject_pack", "public_safe"}
    return normalized if normalized in allowed else "organization"


def ingest_public_fixture() -> tuple[int, int]:
    manifest = load_manifest()
    loaded = 0
    rejected = 0
    access_scope = normalize_access_scope(manifest.get("privacy"))

    with SessionLocal() as db:
        organization = db.scalar(select(Organization).where(Organization.slug == "local-development"))
        if organization is None:
            raise RuntimeError("Run scripts/seed_dev.py before fixture ingestion.")

        for item in manifest["files"]:
            path = FIXTURE_ROOT / item["path"]
            if not path.exists():
                rejected += 1
                continue

            purpose_key = PURPOSE_MAP[item["purpose"]]
            purpose = db.scalar(
                select(FilePurpose).where(
                    FilePurpose.organization_id == organization.id,
                    FilePurpose.key == purpose_key,
                )
            )
            if purpose is None:
                rejected += 1
                continue

            data = path.read_bytes()
            db.add(
                FileArtifact(
                    organization_id=organization.id,
                    file_purpose_id=purpose.id,
                    original_filename=path.name,
                    normalized_filename=path.name,
                    file_extension=path.suffix.lstrip("."),
                    mime_type=mimetypes.guess_type(path.name)[0] or "text/plain",
                    detected_file_category=detect_category(path),
                    file_size_bytes=len(data),
                    checksum_sha256=hashlib.sha256(data).hexdigest(),
                    storage_uri=f"fixture://public/python_score_summary/{item['path']}",
                    import_source="public_fixture",
                    source_type="fixture_import",
                    source_format=detect_source_format(path),
                    access_scope=access_scope,
                    parser_support_status="unknown",
                    status="active",
                    metadata_payload={
                        "manifest_purpose": item["purpose"],
                        "description": item.get("description"),
                        "expected_profile": item.get("expected_profile"),
                    },
                )
            )
            loaded += 1

        db.commit()
        total_artifacts = db.scalar(select(func.count()).select_from(FileArtifact))

    print(f"manifest_files={len(manifest['files'])}")
    print(f"loaded_files={loaded}")
    print(f"rejected_files={rejected}")
    print(f"database_file_artifacts={total_artifacts}")
    return loaded, rejected


if __name__ == "__main__":
    loaded_files, rejected_files = ingest_public_fixture()
    raise SystemExit(0 if loaded_files > 0 and rejected_files == 0 else 1)
