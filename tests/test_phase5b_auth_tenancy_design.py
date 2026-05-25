import uuid

import pytest

from app.pilot.authz import (
    DB_BACKED_ROUTE_PERMISSIONS,
    PilotAuthContext,
    PilotAuthorizationError,
    PilotPermission,
    PilotRole,
    PilotRouteNotReadyError,
    TenantScopedResource,
    authorize_tenant_resource,
    permissions_for_roles,
    require_db_route_readiness,
)
from app.pilot.http_api import pilot_http_route_summary


def auth_context(*, organization_id: uuid.UUID, roles: frozenset[PilotRole]) -> PilotAuthContext:
    return PilotAuthContext(
        actor_user_id=uuid.uuid4(),
        organization_id=organization_id,
        roles=roles,
        request_id="phase5b-test",
    )


def test_role_permissions_are_explicit_and_conservative() -> None:
    read_only_permissions = permissions_for_roles(frozenset({PilotRole.READ_ONLY}))
    reviewer_permissions = permissions_for_roles(frozenset({PilotRole.REVIEWER}))
    teacher_permissions = permissions_for_roles(frozenset({PilotRole.TEACHER}))

    assert PilotPermission.READ_GRADING_EXPORTS in read_only_permissions
    assert PilotPermission.WRITE_ANSWER_KEYS not in read_only_permissions
    assert PilotPermission.READ_REVIEW_QUEUE in reviewer_permissions
    assert PilotPermission.WRITE_RUBRIC_DRAFTS not in reviewer_permissions
    assert PilotPermission.WRITE_RUBRIC_DRAFTS in teacher_permissions


def test_tenant_resource_authorization_requires_same_organization_and_permission() -> None:
    organization_id = uuid.uuid4()
    context = auth_context(organization_id=organization_id, roles=frozenset({PilotRole.REVIEWER}))
    resource = TenantScopedResource(
        organization_id=organization_id,
        resource_type="grading_result",
        resource_id=uuid.uuid4(),
    )

    authorize_tenant_resource(
        context=context,
        resource=resource,
        permission=PilotPermission.READ_GRADING_EXPORTS,
    )

    with pytest.raises(PilotAuthorizationError, match="outside the request organization"):
        authorize_tenant_resource(
            context=context,
            resource=TenantScopedResource(
                organization_id=uuid.uuid4(),
                resource_type="grading_result",
                resource_id=resource.resource_id,
            ),
            permission=PilotPermission.READ_GRADING_EXPORTS,
        )

    with pytest.raises(PilotAuthorizationError, match="Missing required permission"):
        authorize_tenant_resource(
            context=context,
            resource=resource,
            permission=PilotPermission.WRITE_RUBRIC_DRAFTS,
        )


def test_db_backed_routes_require_policy_and_auth_context_before_http_exposure() -> None:
    assert DB_BACKED_ROUTE_PERMISSIONS["/pilot/review-tasks"] == PilotPermission.READ_REVIEW_QUEUE

    with pytest.raises(PilotRouteNotReadyError, match="requires production auth context"):
        require_db_route_readiness(path_template="/pilot/review-tasks", context=None)

    with pytest.raises(PilotRouteNotReadyError, match="No DB-backed route policy"):
        require_db_route_readiness(path_template="/pilot/unknown-db-route", context=None)


def test_current_http_routes_remain_public_safe_and_not_db_backed() -> None:
    db_backed_paths = set(DB_BACKED_ROUTE_PERMISSIONS)

    for route in pilot_http_route_summary():
        assert route["auth_required"] is False
        assert route["data_boundary"] == "caller_provided_public_safe_manifest"
        assert route["path"] not in db_backed_paths
