from __future__ import annotations

import json
from argparse import ArgumentParser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Sequence

from pydantic import BaseModel, ValidationError

from app.pilot.api_adapters import public_evaluation_baseline_adapter, validate_fixture_manifest_adapter
from app.pilot.contracts import ApiErrorResponse, ApiRouteSummaryResponse


JsonHandler = Callable[[dict[str, Any]], BaseModel]


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: dict[str, Any]
    content_type: str = "application/json"


@dataclass(frozen=True)
class PilotHttpRoute:
    method: str
    path: str
    handler: JsonHandler
    request_contract: str
    response_contract: str
    auth_required: bool
    data_boundary: str


PILOT_HTTP_ROUTE_DEFINITIONS: tuple[PilotHttpRoute, ...] = (
    PilotHttpRoute(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        handler=validate_fixture_manifest_adapter,
        request_contract="FixtureManifestRequest",
        response_contract="FixtureManifestValidationResponse",
        auth_required=False,
        data_boundary="caller_provided_public_safe_manifest",
    ),
    PilotHttpRoute(
        method="POST",
        path="/pilot/evaluation/public-baseline",
        handler=public_evaluation_baseline_adapter,
        request_contract="EvaluationBaselineRequest",
        response_contract="EvaluationBaselineResponse",
        auth_required=False,
        data_boundary="caller_provided_public_safe_manifest",
    ),
)


PILOT_HTTP_ROUTES: dict[tuple[str, str], JsonHandler] = {
    (route.method, route.path): route.handler for route in PILOT_HTTP_ROUTE_DEFINITIONS
}


def dispatch_pilot_request(*, method: str, path: str, raw_body: bytes) -> HttpResponse:
    normalized_method = method.upper()
    if normalized_method == "GET":
        return _dispatch_get(path)

    route = PILOT_HTTP_ROUTES.get((normalized_method, path))
    if route is None:
        method_exists_for_path = any(
            route_path == path for route_method, route_path in PILOT_HTTP_ROUTES if route_method != normalized_method
        )
        if method_exists_for_path:
            return _error_response(405, code="method_not_allowed", message="Method is not allowed for this path.")
        return _error_response(404, code="not_found", message="Route was not found.")

    try:
        payload = _json_body(raw_body)
        response = route(payload)
    except json.JSONDecodeError:
        return _error_response(400, code="invalid_json", message="Request body must be valid JSON.")
    except ValidationError as exc:
        return _error_response(
            422,
            code="validation_error",
            message="Request body failed contract validation.",
            details=_json_safe_errors(exc.errors()),
        )
    except ValueError as exc:
        return _error_response(400, code="bad_request", message=str(exc))

    return _json_response(200, response.model_dump(mode="json"))


def pilot_http_route_summary() -> list[dict[str, Any]]:
    return [
        ApiRouteSummaryResponse(
            method=route.method,
            path=route.path,
            request_contract=route.request_contract,
            response_contract=route.response_contract,
            auth_required=route.auth_required,
            data_boundary=route.data_boundary,
        ).model_dump(mode="json")
        for route in sorted(PILOT_HTTP_ROUTE_DEFINITIONS, key=lambda item: (item.method, item.path))
    ]


def serve_pilot_http_api(*, host: str = "127.0.0.1", port: int = 8080) -> None:
    server = ThreadingHTTPServer((host, port), PilotHttpRequestHandler)
    server.serve_forever()


class PilotHttpRequestHandler(BaseHTTPRequestHandler):
    server_version = "RubriCorePilotHTTP/0.1"

    def do_GET(self) -> None:
        response = dispatch_pilot_request(
            method="GET",
            path=self.path.split("?", 1)[0],
            raw_body=b"",
        )
        self._send_json(response)

    def do_POST(self) -> None:
        response = dispatch_pilot_request(
            method="POST",
            path=self.path.split("?", 1)[0],
            raw_body=self.rfile.read(_content_length(self.headers.get("Content-Length"))),
        )
        self._send_json(response)

    def _send_json(self, response: HttpResponse) -> None:
        body = json.dumps(response.body).encode("utf-8")
        self.send_response(response.status_code)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _dispatch_get(path: str) -> HttpResponse:
    if path == "/pilot/health":
        return _json_response(200, {"status": "ok", "service": "pilot_http_api"})
    if path == "/pilot/routes":
        return _json_response(200, {"routes": pilot_http_route_summary()})
    return _error_response(404, code="not_found", message="Route was not found.")


def _json_body(raw_body: bytes) -> dict[str, Any]:
    decoded = json.loads(raw_body.decode("utf-8") if raw_body else "{}")
    if not isinstance(decoded, dict):
        raise ValueError("Request body must be a JSON object.")
    return decoded


def _json_response(status_code: int, body: dict[str, Any]) -> HttpResponse:
    return HttpResponse(status_code=status_code, body=body)


def _error_response(
    status_code: int,
    *,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> HttpResponse:
    return _json_response(
        status_code,
        {
            "error": ApiErrorResponse(code=code, message=message, details=details).model_dump(mode="json"),
        },
    )


def _json_safe_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    return json.loads(json.dumps(errors, default=str))


def _content_length(value: str | None) -> int:
    if value is None:
        return 0
    return max(0, int(value))


if __name__ == "__main__":
    parser = ArgumentParser(description="Run the local RubriCore pilot HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    serve_pilot_http_api(host=args.host, port=args.port)
