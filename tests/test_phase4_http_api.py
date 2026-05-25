import json
from pathlib import Path

from app.pilot.http_api import PILOT_HTTP_ROUTES, dispatch_pilot_request


PUBLIC_EVALUATION_MANIFEST = (
    Path(__file__).parent / "fixtures/public/python_score_summary/evaluation_cases/manifest.json"
)


def fixture_manifest_payload() -> dict:
    return {
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
    }


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_http_routes_include_only_low_risk_phase4_group() -> None:
    assert set(PILOT_HTTP_ROUTES) == {
        ("POST", "/pilot/fixtures/manifest/validate"),
        ("POST", "/pilot/evaluation/public-baseline"),
    }


def test_health_and_routes_http_endpoints_are_transport_only() -> None:
    health = dispatch_pilot_request(method="GET", path="/pilot/health", raw_body=b"")
    routes = dispatch_pilot_request(method="GET", path="/pilot/routes", raw_body=b"")

    assert health.status_code == 200
    assert health.body == {"status": "ok", "service": "pilot_http_api"}
    assert routes.status_code == 200
    assert routes.body == {
        "routes": [
            {
                "method": "POST",
                "path": "/pilot/evaluation/public-baseline",
                "request_contract": "EvaluationBaselineRequest",
                "response_contract": "EvaluationBaselineResponse",
                "auth_required": False,
                "data_boundary": "caller_provided_public_safe_manifest",
            },
            {
                "method": "POST",
                "path": "/pilot/fixtures/manifest/validate",
                "request_contract": "FixtureManifestRequest",
                "response_contract": "FixtureManifestValidationResponse",
                "auth_required": False,
                "data_boundary": "caller_provided_public_safe_manifest",
            },
        ]
    }


def test_fixture_manifest_http_route_delegates_to_public_safe_adapter() -> None:
    response = dispatch_pilot_request(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        raw_body=json_bytes(fixture_manifest_payload()),
    )

    assert response.status_code == 200
    assert response.body == {"validation_errors": []}


def test_fixture_manifest_http_route_rejects_sensitive_markers() -> None:
    payload = fixture_manifest_payload()
    payload["files"][0]["description"] = "Contains real_student material."

    response = dispatch_pilot_request(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        raw_body=json_bytes(payload),
    )

    assert response.status_code == 200
    assert any("sensitive marker" in error for error in response.body["validation_errors"])


def test_public_evaluation_baseline_http_route_uses_public_manifest_payload() -> None:
    manifest = json.loads(PUBLIC_EVALUATION_MANIFEST.read_text(encoding="utf-8"))

    response = dispatch_pilot_request(
        method="POST",
        path="/pilot/evaluation/public-baseline",
        raw_body=json_bytes({"manifest": manifest}),
    )

    assert response.status_code == 200
    assert response.body["validation_errors"] == []
    assert response.body["report"]["passed_count"] == 2
    assert "/fixtures/public/" in PUBLIC_EVALUATION_MANIFEST.as_posix()


def test_http_boundary_maps_transport_errors_without_business_logic() -> None:
    invalid_json = dispatch_pilot_request(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        raw_body=b"{",
    )
    missing_field = dispatch_pilot_request(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        raw_body=json_bytes({"fixture_set": "demo"}),
    )
    missing_route = dispatch_pilot_request(
        method="POST",
        path="/pilot/provider/run",
        raw_body=json_bytes({}),
    )
    wrong_method = dispatch_pilot_request(
        method="PUT",
        path="/pilot/fixtures/manifest/validate",
        raw_body=b"",
    )

    assert invalid_json.status_code == 400
    assert invalid_json.body["error"]["code"] == "invalid_json"
    assert missing_field.status_code == 422
    assert missing_field.body["error"]["code"] == "validation_error"
    assert missing_route.status_code == 404
    assert missing_route.body["error"]["code"] == "not_found"
    assert wrong_method.status_code == 405
    assert wrong_method.body["error"]["code"] == "method_not_allowed"
