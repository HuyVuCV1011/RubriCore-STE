import json

from app.pilot.contracts import ApiErrorResponse, ApiRouteSummaryResponse
from app.pilot.http_api import dispatch_pilot_request, pilot_http_route_summary


def test_route_metadata_declares_contracts_auth_and_data_boundaries() -> None:
    routes = pilot_http_route_summary()

    assert routes == [
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
    assert [ApiRouteSummaryResponse.model_validate(route) for route in routes]


def test_transport_errors_use_stable_error_contract() -> None:
    response = dispatch_pilot_request(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        raw_body=json.dumps({"fixture_set": "demo"}).encode("utf-8"),
    )

    assert response.status_code == 422
    error = ApiErrorResponse.model_validate(response.body["error"])
    assert error.code == "validation_error"
    assert error.message == "Request body failed contract validation."
    assert isinstance(error.details, list)


def test_bad_json_object_shape_uses_bad_request_envelope() -> None:
    response = dispatch_pilot_request(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        raw_body=b"[]",
    )

    assert response.status_code == 400
    assert response.body == {
        "error": {
            "code": "bad_request",
            "message": "Request body must be a JSON object.",
            "details": None,
        }
    }
