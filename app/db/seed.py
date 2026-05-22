from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AssessmentType,
    EvidenceType,
    FilePurpose,
    Organization,
    OutputType,
    RubricType,
    SubjectPack,
    User,
)
from app.db.session import SessionLocal
from app.taxonomy import AssessmentTypeKey, EvidenceTypeKey, OutputTypeKey, RubricTypeKey


LOCAL_ORG_SLUG = "local-development"
LOCAL_ADMIN_EMAIL = "admin@example.local"


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


def _get_or_create_admin(db: Session, organization: Organization) -> None:
    user = db.scalar(
        select(User).where(
            User.organization_id == organization.id,
            User.email == LOCAL_ADMIN_EMAIL,
        )
    )
    if user is not None:
        return

    db.add(
        User(
            organization_id=organization.id,
            email=LOCAL_ADMIN_EMAIL,
            display_name="Development Admin",
            role="admin",
            status="active",
        )
    )


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


def seed_development_data() -> None:
    settings = get_settings()
    if settings.is_production:
        raise RuntimeError("Refusing to seed development data in production.")

    with SessionLocal() as db:
        organization = _get_or_create_organization(db)
        _get_or_create_admin(db, organization)
        _seed_assessment_types(db, organization)
        _seed_evidence_types(db, organization)
        _seed_output_types(db, organization)
        _seed_rubric_types(db, organization)
        _seed_file_purposes(db, organization)
        _seed_subject_pack(db, organization)
        db.commit()


if __name__ == "__main__":
    seed_development_data()
