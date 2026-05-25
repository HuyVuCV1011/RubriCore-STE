from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
README = PROJECT_ROOT / "README.md"
PHASE6C_DOC = PROJECT_ROOT / "docs/logic/21-phase6c-production-auth-provider-selection.md"
PHASE6D_DOC = PROJECT_ROOT / "docs/logic/22-phase6d-current-schema-auth-readiness.md"


def test_phase6d_current_schema_auth_doc_is_linked_from_readme_and_previous_phase() -> None:
    readme = README.read_text(encoding="utf-8")
    phase6c = PHASE6C_DOC.read_text(encoding="utf-8")

    assert "docs/logic/22-phase6d-current-schema-auth-readiness.md" in readme
    assert "22-phase6d-current-schema-auth-readiness.md" in phase6c


def test_phase6d_current_schema_auth_doc_defines_narrow_resolution_path() -> None:
    text = PHASE6D_DOC.read_text(encoding="utf-8")

    required_phrases = [
        "Use the existing organization-scoped `users` table",
        "`one User row represents one actor in one Organization`",
        "`users.organization_id`",
        "`users.role`",
        "`users.status`",
        "load active User by organization and email",
        "`User.status` must be `active`",
        "`users.role` to `PilotRole` mapping is documented",
    ]

    for phrase in required_phrases:
        assert phrase in text


def test_phase6d_current_schema_auth_doc_defers_migrations_with_triggers() -> None:
    text = PHASE6D_DOC.read_text(encoding="utf-8")

    required_phrases = [
        "migrations can be deferred",
        "one person can access multiple organizations without duplicate user rows",
        "login must be keyed by provider `issuer` and `subject` rather than email",
        "users can change email without breaking login identity",
        "tenant access must be revoked independently from the user record",
        "docs clearly state that migrations are deferred, not rejected",
    ]

    for phrase in required_phrases:
        assert phrase in text


def test_phase6d_current_schema_auth_doc_does_not_implement_real_auth_or_schema() -> None:
    text = PHASE6D_DOC.read_text(encoding="utf-8")

    deferred_phrases = [
        "Phase 6D is a design slice only.",
        "JWT verification code",
        "external identity tables",
        "organization membership tables",
        "schema changes or Alembic migrations",
        "secrets or credentials",
        "new dependencies",
        "new DB-backed routes",
    ]

    for phrase in deferred_phrases:
        assert phrase in text
