from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
README = PROJECT_ROOT / "README.md"
PHASE5C_DOC = PROJECT_ROOT / "docs/logic/18-phase5c-production-auth-implementation-plan.md"
PHASE5B_DOC = PROJECT_ROOT / "docs/logic/17-phase5b-auth-tenancy-design.md"


def test_phase5c_auth_plan_is_linked_from_readme_and_previous_phase() -> None:
    readme = README.read_text(encoding="utf-8")
    phase5b = PHASE5B_DOC.read_text(encoding="utf-8")

    assert "docs/logic/18-phase5c-production-auth-implementation-plan.md" in readme
    assert "18-phase5c-production-auth-implementation-plan.md" in phase5b


def test_phase5c_auth_plan_defines_required_security_boundaries() -> None:
    text = PHASE5C_DOC.read_text(encoding="utf-8")

    required_phrases = [
        "verified `PilotAuthContext`",
        "OIDC/JWT bearer tokens",
        "tenant-scoped DB loading",
        "load_grading_result_for_org",
        "`GET /pilot/subject-packs/{key}`",
        "Do not expose these routes until the first auth-backed route is proven",
        "Do not add a framework just to keep adding public-safe DB-free routes.",
    ]

    for phrase in required_phrases:
        assert phrase in text
