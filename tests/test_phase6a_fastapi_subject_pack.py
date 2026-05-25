import uuid

from fastapi.testclient import TestClient

from app.db.models import SubjectPack
from app.pilot.authz import PilotAuthContext, PilotRole
from app.pilot.fastapi_app import create_app, get_fastapi_db, get_pilot_auth_context


class ScalarSession:
    def __init__(self, *results: object | None) -> None:
        self.results = list(results)

    def scalar(self, _: object) -> object | None:
        return self.results.pop(0) if self.results else None


def subject_pack(*, organization_id: uuid.UUID | None, key: str = "python-pilot") -> SubjectPack:
    return SubjectPack(
        id=uuid.uuid4(),
        organization_id=organization_id,
        key=key,
        name="Python Pilot",
        schema_version="1.0",
        config={
            "schema_version": "1.0",
            "assessment_types": ["code-assignment"],
            "evidence_types": ["code"],
            "output_types": ["executable-behavior"],
            "rubric_types": ["analytic-rubric"],
        },
        status="active",
    )


def test_fastapi_public_routes_wrap_existing_public_safe_adapters() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/pilot/fixtures/manifest/validate",
        json={
            "fixture_set": "python-score-summary",
            "title": "Python Score Summary",
            "privacy": "public_safe",
            "files": [
                {
                    "path": "assessment_materials/problem_statement.md",
                    "purpose": "assessment_material",
                    "description": "Synthetic public assignment prompt.",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"validation_errors": []}


def test_fastapi_subject_pack_route_requires_auth_context() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/pilot/subject-packs/python-pilot")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_auth_context"


def test_fastapi_subject_pack_route_uses_auth_dependency_and_tenant_scoped_loader() -> None:
    organization_id = uuid.uuid4()
    app = create_app()
    app.dependency_overrides[get_pilot_auth_context] = lambda: PilotAuthContext(
        actor_user_id=uuid.uuid4(),
        organization_id=organization_id,
        roles=frozenset({PilotRole.READ_ONLY}),
        request_id="phase6a-test",
    )
    app.dependency_overrides[get_fastapi_db] = lambda: ScalarSession(subject_pack(organization_id=organization_id))
    client = TestClient(app)

    response = client.get("/pilot/subject-packs/python-pilot")

    assert response.status_code == 200
    assert response.json() == {
        "id": response.json()["id"],
        "organization_id": str(organization_id),
        "key": "python-pilot",
        "name": "Python Pilot",
        "schema_version": "1.0",
        "status": "active",
        "assessment_types": ["code-assignment"],
        "evidence_types": ["code"],
        "output_types": ["executable-behavior"],
        "rubric_types": ["analytic-rubric"],
    }


def test_fastapi_subject_pack_route_returns_not_found_without_cross_tenant_lookup() -> None:
    organization_id = uuid.uuid4()
    app = create_app()
    app.dependency_overrides[get_pilot_auth_context] = lambda: PilotAuthContext(
        actor_user_id=uuid.uuid4(),
        organization_id=organization_id,
        roles=frozenset({PilotRole.READ_ONLY}),
        request_id="phase6a-test",
    )
    app.dependency_overrides[get_fastapi_db] = lambda: ScalarSession(None, None)
    client = TestClient(app)

    response = client.get("/pilot/subject-packs/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_fastapi_subject_pack_route_allows_global_pack_after_permission_check() -> None:
    organization_id = uuid.uuid4()
    app = create_app()
    app.dependency_overrides[get_pilot_auth_context] = lambda: PilotAuthContext(
        actor_user_id=uuid.uuid4(),
        organization_id=organization_id,
        roles=frozenset({PilotRole.READ_ONLY}),
        request_id="phase6a-test",
    )
    app.dependency_overrides[get_fastapi_db] = lambda: ScalarSession(None, subject_pack(organization_id=None))
    client = TestClient(app)

    response = client.get("/pilot/subject-packs/python-pilot")

    assert response.status_code == 200
    assert response.json()["organization_id"] is None


def test_fastapi_subject_pack_route_rejects_missing_permission() -> None:
    organization_id = uuid.uuid4()
    app = create_app()
    app.dependency_overrides[get_pilot_auth_context] = lambda: PilotAuthContext(
        actor_user_id=uuid.uuid4(),
        organization_id=organization_id,
        roles=frozenset(),
        request_id="phase6a-test",
    )
    app.dependency_overrides[get_fastapi_db] = lambda: ScalarSession(subject_pack(organization_id=organization_id))
    client = TestClient(app)

    response = client.get("/pilot/subject-packs/python-pilot")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
