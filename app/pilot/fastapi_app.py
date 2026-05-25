from __future__ import annotations

import uuid
from collections.abc import Generator
import json
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.services.subject_packs import subject_pack_summary
from app.db.session import get_db
from app.pilot.api_adapters import public_evaluation_baseline_adapter, validate_fixture_manifest_adapter
from app.pilot.authz import PilotAuthContext, PilotAuthorizationError, PilotRole
from app.pilot.contracts import (
    ApiErrorResponse,
    EvaluationBaselineRequest,
    EvaluationBaselineResponse,
    FixtureManifestRequest,
    FixtureManifestValidationResponse,
    SubjectPackSummaryResponse,
)
from app.pilot.db_loaders import load_subject_pack_for_context


def create_app() -> FastAPI:
    app = FastAPI(
        title="RubriCore Pilot API",
        version="0.1.0",
        description="Pilot API boundary for public-safe routes and the first auth-aware DB-backed route.",
    )
    app.add_exception_handler(HTTPException, cast(Any, _http_exception_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, _request_validation_exception_handler))
    app.add_exception_handler(PilotAuthorizationError, cast(Any, _authorization_exception_handler))

    @app.get("/pilot/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "pilot_fastapi"}

    @app.post(
        "/pilot/fixtures/manifest/validate",
        response_model=FixtureManifestValidationResponse,
    )
    def validate_fixture_manifest_route(
        request: FixtureManifestRequest,
    ) -> FixtureManifestValidationResponse:
        return validate_fixture_manifest_adapter(request.model_dump(mode="json"))

    @app.post(
        "/pilot/evaluation/public-baseline",
        response_model=EvaluationBaselineResponse,
    )
    def public_evaluation_baseline_route(
        request: EvaluationBaselineRequest,
    ) -> EvaluationBaselineResponse:
        return public_evaluation_baseline_adapter(request.model_dump(mode="json"))

    @app.get(
        "/pilot/subject-packs/{key}",
        response_model=SubjectPackSummaryResponse,
    )
    def get_subject_pack_route(
        key: str,
        auth_context: Annotated[PilotAuthContext, Depends(get_pilot_auth_context)],
        db: Annotated[Session, Depends(get_fastapi_db)],
    ) -> SubjectPackSummaryResponse:
        pack = load_subject_pack_for_context(db, key=key, context=auth_context)
        if pack is None:
            raise _api_http_exception(404, code="not_found", message="Subject pack was not found.")
        return SubjectPackSummaryResponse.model_validate(subject_pack_summary(pack))

    return app


def get_pilot_auth_context(
    x_pilot_actor_user_id: Annotated[str | None, Header()] = None,
    x_pilot_organization_id: Annotated[str | None, Header()] = None,
    x_pilot_roles: Annotated[str | None, Header()] = None,
    x_pilot_request_id: Annotated[str | None, Header()] = None,
) -> PilotAuthContext:
    if not x_pilot_actor_user_id or not x_pilot_organization_id or not x_pilot_roles:
        raise _api_http_exception(401, code="missing_auth_context", message="Pilot auth context headers are required.")

    try:
        roles = frozenset(PilotRole(role.strip()) for role in x_pilot_roles.split(",") if role.strip())
        if not roles:
            raise ValueError("At least one role is required.")
        return PilotAuthContext(
            actor_user_id=uuid.UUID(x_pilot_actor_user_id),
            organization_id=uuid.UUID(x_pilot_organization_id),
            roles=roles,
            request_id=x_pilot_request_id,
        )
    except (ValueError, ValidationError) as exc:
        raise _api_http_exception(401, code="invalid_auth_context", message=str(exc)) from exc


def get_fastapi_db() -> Generator[Session, None, None]:
    yield from get_db()


async def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code="http_error", message=str(detail)),
    )


async def _request_validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_body(
            code="validation_error",
            message="Request failed validation.",
            details=_json_safe_errors(exc.errors()),
        ),
    )


async def _authorization_exception_handler(_: Request, exc: PilotAuthorizationError) -> JSONResponse:
    return JSONResponse(status_code=403, content=_error_body(code="forbidden", message=str(exc)))


def _api_http_exception(status_code: int, *, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=_error_body(code=code, message=message))


def _error_body(
    *,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"error": ApiErrorResponse(code=code, message=message, details=details).model_dump(mode="json")}


def _json_safe_errors(errors: Any) -> list[dict[str, Any]]:
    return json.loads(json.dumps(errors, default=str))


app = create_app()
