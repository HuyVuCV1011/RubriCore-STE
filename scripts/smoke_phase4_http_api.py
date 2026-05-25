from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
from typing import Any, cast

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.pilot.http_api import PilotHttpRequestHandler, dispatch_pilot_request  # noqa: E402


PUBLIC_EVALUATION_MANIFEST = (
    PROJECT_ROOT / "tests/fixtures/public/python_score_summary/evaluation_cases/manifest.json"
)


def main() -> None:
    summary = run_phase4_http_smoke()
    print(json.dumps(summary, indent=2, sort_keys=True))


def run_phase4_http_smoke() -> dict[str, Any]:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), PilotHttpRequestHandler)
    except PermissionError:
        return _run_dispatcher_smoke()

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = cast(tuple[str, int], server.server_address)
    try:
        health = _request_json(host=host, port=port, method="GET", path="/pilot/health")
        manifest_validation = _request_json(
            host=host,
            port=port,
            method="POST",
            path="/pilot/fixtures/manifest/validate",
            payload=_fixture_manifest_payload(),
        )
        baseline = _request_json(
            host=host,
            port=port,
            method="POST",
            path="/pilot/evaluation/public-baseline",
            payload={"manifest": _load_public_evaluation_manifest()},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    _assert_smoke_response(health, manifest_validation, baseline)
    return {
        "transport": "http_server",
        "health": health["body"],
        "manifest_validation": manifest_validation["body"],
        "baseline_summary": {
            "validation_errors": baseline["body"]["validation_errors"],
            "case_count": baseline["body"]["report"]["case_count"],
            "passed_count": baseline["body"]["report"]["passed_count"],
            "failed_count": baseline["body"]["report"]["failed_count"],
        },
    }


def _run_dispatcher_smoke() -> dict[str, Any]:
    health = _dispatch_json(method="GET", path="/pilot/health")
    manifest_validation = _dispatch_json(
        method="POST",
        path="/pilot/fixtures/manifest/validate",
        payload=_fixture_manifest_payload(),
    )
    baseline = _dispatch_json(
        method="POST",
        path="/pilot/evaluation/public-baseline",
        payload={"manifest": _load_public_evaluation_manifest()},
    )

    _assert_smoke_response(health, manifest_validation, baseline)
    return {
        "transport": "dispatcher_fallback",
        "health": health["body"],
        "manifest_validation": manifest_validation["body"],
        "baseline_summary": {
            "validation_errors": baseline["body"]["validation_errors"],
            "case_count": baseline["body"]["report"]["case_count"],
            "passed_count": baseline["body"]["report"]["passed_count"],
            "failed_count": baseline["body"]["report"]["failed_count"],
        },
    }


def _dispatch_json(
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    response = dispatch_pilot_request(method=method, path=path, raw_body=raw_body)
    return {"status_code": response.status_code, "body": response.body}


def _request_json(
    *,
    host: str,
    port: int,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection = HTTPConnection(host, port, timeout=10)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read().decode("utf-8")
        return {
            "status_code": response.status,
            "body": json.loads(response_body),
        }
    finally:
        connection.close()


def _assert_smoke_response(
    health: dict[str, Any],
    manifest_validation: dict[str, Any],
    baseline: dict[str, Any],
) -> None:
    if health["status_code"] != 200 or health["body"] != {"status": "ok", "service": "pilot_http_api"}:
        raise SystemExit(f"Health smoke failed: {health}")
    if manifest_validation["status_code"] != 200 or manifest_validation["body"]["validation_errors"]:
        raise SystemExit(f"Fixture validation smoke failed: {manifest_validation}")
    report = baseline["body"].get("report")
    if baseline["status_code"] != 200 or baseline["body"]["validation_errors"] or report is None:
        raise SystemExit(f"Public baseline smoke failed: {baseline}")
    if report["passed_count"] != report["case_count"] or report["failed_count"] != 0:
        raise SystemExit(f"Public baseline did not pass cleanly: {baseline}")


def _load_public_evaluation_manifest() -> dict[str, Any]:
    return json.loads(PUBLIC_EVALUATION_MANIFEST.read_text(encoding="utf-8"))


def _fixture_manifest_payload() -> dict[str, Any]:
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


if __name__ == "__main__":
    main()
