from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
README = PROJECT_ROOT / "README.md"
PHASE6B_DOC = PROJECT_ROOT / "docs/logic/20-phase6b-auth-provider-adapter.md"
PHASE6C_DOC = PROJECT_ROOT / "docs/logic/21-phase6c-production-auth-provider-selection.md"


def test_phase6c_auth_provider_selection_doc_is_linked_from_readme_and_previous_phase() -> None:
    readme = README.read_text(encoding="utf-8")
    phase6b = PHASE6B_DOC.read_text(encoding="utf-8")

    assert "docs/logic/21-phase6c-production-auth-provider-selection.md" in readme
    assert "21-phase6c-production-auth-provider-selection.md" in phase6b


def test_phase6c_auth_provider_selection_doc_defines_future_oidc_jwt_boundary() -> None:
    text = PHASE6C_DOC.read_text(encoding="utf-8")

    required_phrases = [
        "Use OIDC/JWT bearer tokens as the first production auth provider style.",
        "`AuthProvider.verify_request(headers) -> PilotAuthContext`",
        "issuer",
        "audience",
        "JWKS URL",
        "allowed algorithms",
        "provider subject claim",
        "Prefer DB-backed membership lookup for production authorization.",
        "Missing bearer token",
        "Invalid signature or unknown key",
        "Expired or not-yet-valid token",
    ]

    for phrase in required_phrases:
        assert phrase in text


def test_phase6c_auth_provider_selection_doc_does_not_implement_real_auth() -> None:
    text = PHASE6C_DOC.read_text(encoding="utf-8")

    deferred_phrases = [
        "Phase 6C is a design slice only.",
        "JWT verification code",
        "JWKS fetching or caching",
        "secrets or credentials",
        "schema changes or Alembic migrations",
        "docs clearly state that no real auth provider or token verification was added",
    ]

    for phrase in deferred_phrases:
        assert phrase in text
