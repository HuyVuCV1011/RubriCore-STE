from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
README = PROJECT_ROOT / "README.md"
PHASE6A_DOC = PROJECT_ROOT / "docs/logic/19-phase6a-fastapi-subject-pack-route.md"
PHASE6B_DOC = PROJECT_ROOT / "docs/logic/20-phase6b-auth-provider-adapter.md"


def test_phase6b_auth_provider_doc_is_linked_from_readme_and_previous_phase() -> None:
    readme = README.read_text(encoding="utf-8")
    phase6a = PHASE6A_DOC.read_text(encoding="utf-8")

    assert "docs/logic/20-phase6b-auth-provider-adapter.md" in readme
    assert "app.pilot.auth_provider" in phase6a


def test_phase6b_auth_provider_doc_keeps_real_auth_deferred() -> None:
    text = PHASE6B_DOC.read_text(encoding="utf-8")

    required_phrases = [
        "`AuthProvider.verify_request(headers) -> PilotAuthContext`",
        "`PilotHeaderAuthProvider`",
        "These headers remain development and test wiring only.",
        "OAuth/OIDC/JWT verification",
        "secrets or credentials",
        "network calls",
        "new dependencies",
        "schema changes or Alembic migrations",
    ]

    for phrase in required_phrases:
        assert phrase in text
