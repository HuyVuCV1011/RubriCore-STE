from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AssessmentType,
    EvidenceType,
    FilePurpose,
    Organization,
    RubricType,
    SubjectPack,
    User,
)
from app.db.session import SessionLocal


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
        ("multiple-choice", "Multiple Choice"),
        ("numeric-answer", "Numeric Answer"),
        ("short-answer", "Short Answer"),
        ("constructed-response", "Constructed Response"),
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
        ("text", "Text"),
        ("numeric", "Numeric"),
        ("selected-option", "Selected Option"),
        ("file-metadata", "File Metadata"),
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


def _seed_rubric_types(db: Session, organization: Organization) -> None:
    records = [
        ("binary-key", "Binary Key"),
        ("checklist", "Checklist"),
        ("analytic-rubric", "Analytic Rubric"),
        ("criterion-weighted-rubric", "Criterion Weighted Rubric"),
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
        ("assessment-material", "Assessment Material"),
        ("answer-key-source", "Answer Key Source"),
        ("submission-evidence", "Submission Evidence"),
        ("reference-solution", "Reference Solution"),
        ("extracted-representation", "Extracted Representation"),
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
        _seed_rubric_types(db, organization)
        _seed_file_purposes(db, organization)
        _seed_subject_pack(db, organization)
        db.commit()


if __name__ == "__main__":
    seed_development_data()
