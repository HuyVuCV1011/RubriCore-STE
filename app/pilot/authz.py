from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class PilotRole(StrEnum):
    SYSTEM = "system"
    ADMIN = "admin"
    TEACHER = "teacher"
    REVIEWER = "reviewer"
    READ_ONLY = "read_only"


class PilotPermission(StrEnum):
    READ_SUBJECT_PACKS = "read_subject_packs"
    READ_GRADING_EXPORTS = "read_grading_exports"
    READ_REVIEW_QUEUE = "read_review_queue"
    WRITE_ANSWER_KEYS = "write_answer_keys"
    WRITE_RUBRIC_DRAFTS = "write_rubric_drafts"
    EXPORT_CALIBRATION = "export_calibration"


ROLE_PERMISSIONS: dict[PilotRole, frozenset[PilotPermission]] = {
    PilotRole.SYSTEM: frozenset(PilotPermission),
    PilotRole.ADMIN: frozenset(PilotPermission),
    PilotRole.TEACHER: frozenset(
        {
            PilotPermission.READ_SUBJECT_PACKS,
            PilotPermission.READ_GRADING_EXPORTS,
            PilotPermission.READ_REVIEW_QUEUE,
            PilotPermission.WRITE_ANSWER_KEYS,
            PilotPermission.WRITE_RUBRIC_DRAFTS,
            PilotPermission.EXPORT_CALIBRATION,
        }
    ),
    PilotRole.REVIEWER: frozenset(
        {
            PilotPermission.READ_SUBJECT_PACKS,
            PilotPermission.READ_GRADING_EXPORTS,
            PilotPermission.READ_REVIEW_QUEUE,
            PilotPermission.EXPORT_CALIBRATION,
        }
    ),
    PilotRole.READ_ONLY: frozenset(
        {
            PilotPermission.READ_SUBJECT_PACKS,
            PilotPermission.READ_GRADING_EXPORTS,
        }
    ),
}


DB_BACKED_ROUTE_PERMISSIONS: dict[str, PilotPermission] = {
    "/pilot/subject-packs/{key}": PilotPermission.READ_SUBJECT_PACKS,
    "/pilot/review-tasks": PilotPermission.READ_REVIEW_QUEUE,
    "/pilot/grading-results/{grading_result_id}/export": PilotPermission.READ_GRADING_EXPORTS,
    "/pilot/grading-results/{grading_result_id}/reviewed-example": PilotPermission.EXPORT_CALIBRATION,
    "/pilot/answer-keys": PilotPermission.WRITE_ANSWER_KEYS,
    "/pilot/rubrics/{rubric_id}/draft": PilotPermission.WRITE_RUBRIC_DRAFTS,
}


@dataclass(frozen=True)
class PilotAuthContext:
    actor_user_id: uuid.UUID
    organization_id: uuid.UUID
    roles: frozenset[PilotRole]
    request_id: str | None = None


@dataclass(frozen=True)
class TenantScopedResource:
    organization_id: uuid.UUID
    resource_type: str
    resource_id: uuid.UUID | None = None


class PilotAuthorizationError(PermissionError):
    """Raised when a future DB-backed pilot route fails auth or tenancy checks."""


class PilotRouteNotReadyError(RuntimeError):
    """Raised when a DB-backed route is attempted before production auth is implemented."""


def permissions_for_roles(roles: frozenset[PilotRole]) -> frozenset[PilotPermission]:
    permissions: set[PilotPermission] = set()
    for role in roles:
        permissions.update(ROLE_PERMISSIONS[role])
    return frozenset(permissions)


def require_permission(context: PilotAuthContext, permission: PilotPermission) -> None:
    if permission not in permissions_for_roles(context.roles):
        raise PilotAuthorizationError(f"Missing required permission: {permission}.")


def require_same_tenant(context: PilotAuthContext, resource: TenantScopedResource) -> None:
    if context.organization_id != resource.organization_id:
        raise PilotAuthorizationError(
            f"Cannot access {resource.resource_type} outside the request organization boundary."
        )


def authorize_tenant_resource(
    *,
    context: PilotAuthContext,
    resource: TenantScopedResource,
    permission: PilotPermission,
) -> None:
    require_same_tenant(context, resource)
    require_permission(context, permission)


def require_db_route_readiness(*, path_template: str, context: PilotAuthContext | None) -> None:
    permission = DB_BACKED_ROUTE_PERMISSIONS.get(path_template)
    if permission is None:
        raise PilotRouteNotReadyError(f"No DB-backed route policy is defined for {path_template}.")
    if context is None:
        raise PilotRouteNotReadyError(
            f"{path_template} requires production auth context before it can be exposed over HTTP."
        )
    require_permission(context, permission)
