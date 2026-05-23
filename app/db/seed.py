import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AssessmentType,
    EvidenceType,
    FilePurpose,
    KnowledgeSource,
    Organization,
    OutputType,
    Rubric,
    RubricType,
    SubjectPack,
    User,
)
from app.db.services.knowledge_library import (
    convert_knowledge_source_to_markdown,
    create_knowledge_chunks,
    register_knowledge_source,
)
from app.db.services.rubrics import create_rubric, publish_rubric_version
from app.db.session import SessionLocal
from app.taxonomy import AssessmentTypeKey, EvidenceTypeKey, OutputTypeKey, RubricTypeKey


LOCAL_ORG_SLUG = "local-development"
LOCAL_ADMIN_EMAIL = "admin@example.local"
PYTHON_SCORE_SUMMARY_FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/public/python_score_summary"


def _get_or_create_organization(db: Session) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.slug == LOCAL_ORG_SLUG))
    if organization is not None:
        return organization

    organization = Organization(
        name="Local Development Organization",
        slug=LOCAL_ORG_SLUG,
        status="active",
    )
    db.add(organization)
    db.flush()
    return organization


def _get_or_create_admin(db: Session, organization: Organization) -> User:
    user = db.scalar(
        select(User).where(
            User.organization_id == organization.id,
            User.email == LOCAL_ADMIN_EMAIL,
        )
    )
    if user is not None:
        return user

    user = User(
        organization_id=organization.id,
        email=LOCAL_ADMIN_EMAIL,
        display_name="Development Admin",
        role="admin",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


def _seed_assessment_types(db: Session, organization: Organization) -> None:
    records = [
        (AssessmentTypeKey.MULTIPLE_CHOICE.value, "Multiple Choice"),
        (AssessmentTypeKey.NUMERIC_ANSWER.value, "Numeric Answer"),
        (AssessmentTypeKey.SHORT_ANSWER.value, "Short Answer"),
        (AssessmentTypeKey.CONSTRUCTED_RESPONSE.value, "Constructed Response"),
        (AssessmentTypeKey.CODE_ASSIGNMENT.value, "Code Assignment"),
    ]
    for key, name in records:
        exists = db.scalar(
            select(AssessmentType).where(
                AssessmentType.organization_id == organization.id,
                AssessmentType.key == key,
            )
        )
        if exists is None:
            db.add(
                AssessmentType(
                    organization_id=organization.id,
                    key=key,
                    name=name,
                    config={"schema_version": "1.0"},
                    status="active",
                )
            )


def _seed_evidence_types(db: Session, organization: Organization) -> None:
    records = [
        (EvidenceTypeKey.TEXT.value, "Text"),
        (EvidenceTypeKey.NUMERIC.value, "Numeric"),
        (EvidenceTypeKey.SELECTED_OPTION.value, "Selected Option"),
        (EvidenceTypeKey.FILE_ARTIFACT.value, "File Artifact"),
        (EvidenceTypeKey.CODE.value, "Code"),
    ]
    for key, name in records:
        exists = db.scalar(
            select(EvidenceType).where(
                EvidenceType.organization_id == organization.id,
                EvidenceType.key == key,
            )
        )
        if exists is None:
            db.add(
                EvidenceType(
                    organization_id=organization.id,
                    key=key,
                    name=name,
                    config={"schema_version": "1.0"},
                    status="active",
                )
            )


def _seed_output_types(db: Session, organization: Organization) -> None:
    records = [
        (OutputTypeKey.EXACT_ANSWER.value, "Exact Answer"),
        (OutputTypeKey.SELECTED_OPTION.value, "Selected Option"),
        (OutputTypeKey.NUMERIC_VALUE.value, "Numeric Value"),
        (OutputTypeKey.NUMERIC_VALUE_WITH_UNIT.value, "Numeric Value With Unit"),
        (OutputTypeKey.SHORT_TEXT.value, "Short Text"),
        (OutputTypeKey.LONG_TEXT.value, "Long Text"),
        (OutputTypeKey.STRUCTURED_EXPLANATION.value, "Structured Explanation"),
        (OutputTypeKey.EXECUTABLE_BEHAVIOR.value, "Executable Behavior"),
        (OutputTypeKey.CODE_OUTPUT.value, "Code Output"),
        (OutputTypeKey.FILE_ARTIFACT.value, "File Artifact"),
        (OutputTypeKey.MIXED_OUTPUT.value, "Mixed Output"),
    ]
    for key, name in records:
        exists = db.scalar(
            select(OutputType).where(
                OutputType.organization_id == organization.id,
                OutputType.key == key,
            )
        )
        if exists is None:
            db.add(
                OutputType(
                    organization_id=organization.id,
                    key=key,
                    name=name,
                    config={"schema_version": "1.0"},
                    status="active",
                )
            )


def _seed_rubric_types(db: Session, organization: Organization) -> None:
    records = [
        (RubricTypeKey.BINARY_KEY.value, "Binary Key"),
        (RubricTypeKey.CHECKLIST.value, "Checklist"),
        (RubricTypeKey.ANALYTIC_RUBRIC.value, "Analytic Rubric"),
        (RubricTypeKey.HOLISTIC_RUBRIC.value, "Holistic Rubric"),
        (RubricTypeKey.CRITERION_WEIGHTED_RUBRIC.value, "Criterion Weighted Rubric"),
    ]
    for key, name in records:
        exists = db.scalar(
            select(RubricType).where(
                RubricType.organization_id == organization.id,
                RubricType.key == key,
            )
        )
        if exists is None:
            db.add(
                RubricType(
                    organization_id=organization.id,
                    key=key,
                    name=name,
                    config={"schema_version": "1.0"},
                    status="active",
                )
            )


def _seed_file_purposes(db: Session, organization: Organization) -> None:
    records = [
        ("assessment_material", "Assessment Material"),
        ("answer_key_source", "Answer Key Source"),
        ("submission_evidence", "Submission Evidence"),
        ("reference_solution", "Reference Solution"),
        ("extracted_representation", "Extracted Representation"),
        ("rubric_source", "Rubric Source"),
        ("knowledge_source", "Knowledge Source"),
        ("converted_markdown", "Converted Markdown"),
    ]
    for key, name in records:
        exists = db.scalar(
            select(FilePurpose).where(
                FilePurpose.organization_id == organization.id,
                FilePurpose.key == key,
            )
        )
        if exists is None:
            db.add(
                FilePurpose(
                    organization_id=organization.id,
                    key=key,
                    name=name,
                    config={"schema_version": "1.0"},
                    status="active",
                )
            )


def _seed_subject_pack(db: Session, organization: Organization) -> None:
    exists = db.scalar(
        select(SubjectPack).where(
            SubjectPack.organization_id == organization.id,
            SubjectPack.key == "generic-development",
        )
    )
    if exists is not None:
        return

    db.add(
        SubjectPack(
            organization_id=organization.id,
            key="generic-development",
            name="Generic Development Pack",
            description="Safe placeholder subject pack for local development.",
            schema_version="1.0",
            config={"schema_version": "1.0", "assessment_types": [], "evidence_types": []},
            status="active",
        )
    )


def _seed_demo_rubric(db: Session, organization: Organization, admin: User) -> None:
    exists = db.scalar(
        select(Rubric).where(
            Rubric.organization_id == organization.id,
            Rubric.slug == "python-score-summary-demo",
        )
    )
    if exists is not None:
        return

    rubric_type = db.scalar(
        select(RubricType).where(
            RubricType.organization_id == organization.id,
            RubricType.key == RubricTypeKey.ANALYTIC_RUBRIC.value,
        )
    )
    if rubric_type is None:
        raise RuntimeError("Analytic rubric type must be seeded before demo rubric.")

    draft_schema = {
        "schema_version": "1.0",
        "criteria": [
            {
                "key": "correctness",
                "label": "Correctness",
                "description": "The solution computes the requested score summary accurately.",
                "weight": "2",
                "position": 0,
                "evaluation_hints": {"deterministic_checks": ["unit_tests_pass"]},
            },
            {
                "key": "clarity",
                "label": "Clarity",
                "description": "The solution is readable and uses clear names for the data flow.",
                "weight": "1",
                "position": 1,
            },
        ],
        "performance_levels": [
            {"key": "needs_revision", "label": "Needs Revision", "score": "0", "position": 0},
            {"key": "partial", "label": "Partial", "score": "1", "position": 1},
            {"key": "meets", "label": "Meets", "score": "2", "position": 2},
        ],
        "descriptors": [
            {
                "criterion_key": "correctness",
                "performance_level_key": "needs_revision",
                "narrative": "Produces incorrect totals or cannot run to completion.",
            },
            {
                "criterion_key": "correctness",
                "performance_level_key": "partial",
                "narrative": "Handles the main path but misses edge cases or summary fields.",
            },
            {
                "criterion_key": "correctness",
                "performance_level_key": "meets",
                "narrative": "Computes the requested summary accurately for representative inputs.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "needs_revision",
                "narrative": "Code structure makes the computation difficult to inspect.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "partial",
                "narrative": "Readable in parts, with some unclear names or unnecessary complexity.",
            },
            {
                "criterion_key": "clarity",
                "performance_level_key": "meets",
                "narrative": "Uses clear names and a straightforward structure.",
            },
        ],
    }

    rubric = create_rubric(
        db,
        organization_id=organization.id,
        rubric_type_id=rubric_type.id,
        created_by_user_id=admin.id,
        title="Python Score Summary Demo Rubric",
        slug="python-score-summary-demo",
        description="Synthetic local-development rubric for the public Python score summary fixture.",
        draft_schema=draft_schema,
        metadata_payload={"fixture": "python_score_summary", "subject_agnostic": True},
    )
    publish_rubric_version(
        db,
        rubric=rubric,
        published_by_user_id=admin.id,
        source_metadata={"source": "seed_dev", "fixture": "python_score_summary"},
    )


def _seed_demo_knowledge_sources(db: Session, organization: Organization, admin: User) -> None:
    manifest_path = PYTHON_SCORE_SUMMARY_FIXTURE / "manifest.json"
    if not manifest_path.exists():
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for file_entry in manifest.get("files", []):
        if file_entry.get("purpose") != "knowledge_source":
            continue

        fixture_path = PYTHON_SCORE_SUMMARY_FIXTURE / file_entry["path"]
        if not fixture_path.exists():
            continue

        title = file_entry.get("description") or fixture_path.stem.replace("_", " ").title()
        exists = db.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.organization_id == organization.id,
                KnowledgeSource.title == title,
                KnowledgeSource.access_scope == "public_safe",
            )
        )
        if exists is not None:
            continue

        content = fixture_path.read_text(encoding="utf-8")
        source = register_knowledge_source(
            db,
            organization_id=organization.id,
            owner_user_id=admin.id,
            title=title,
            source_filename=fixture_path.name,
            source_storage_uri=f"fixture://python_score_summary/{file_entry['path']}",
            access_scope="public_safe",
            source_type="fixture_import",
            summary=file_entry.get("description"),
            metadata_payload={
                "fixture": "python_score_summary",
                "fixture_path": file_entry["path"],
                "knowledge_type": file_entry.get("knowledge_type"),
            },
            actor_source="fixture_import",
            reason="Seed public-safe demo knowledge source.",
        )
        convert_knowledge_source_to_markdown(
            db,
            knowledge_source=source,
            source_filename=fixture_path.name,
            source_content=content,
            markdown_storage_uri=f"derived://fixture/python_score_summary/{fixture_path.stem}.md",
            actor_user_id=admin.id,
            actor_source="fixture_import",
            reason="Seed public-safe demo Markdown conversion.",
        )
        if source.conversion_status == "converted":
            if fixture_path.suffix.lower() in {".md", ".markdown"}:
                markdown_content = content
            else:
                markdown_content = f"# {title}\n\n{content.strip()}\n"
            create_knowledge_chunks(
                db,
                knowledge_source=source,
                markdown_content=markdown_content,
                actor_user_id=admin.id,
                actor_source="fixture_import",
                reason="Seed public-safe demo knowledge chunks.",
            )


def seed_development_data() -> None:
    settings = get_settings()
    if settings.is_production:
        raise RuntimeError("Refusing to seed development data in production.")

    with SessionLocal() as db:
        organization = _get_or_create_organization(db)
        admin = _get_or_create_admin(db, organization)
        _seed_assessment_types(db, organization)
        _seed_evidence_types(db, organization)
        _seed_output_types(db, organization)
        _seed_rubric_types(db, organization)
        _seed_file_purposes(db, organization)
        _seed_subject_pack(db, organization)
        _seed_demo_rubric(db, organization, admin)
        _seed_demo_knowledge_sources(db, organization, admin)
        db.commit()


if __name__ == "__main__":
    seed_development_data()
