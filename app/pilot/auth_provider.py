from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Protocol

from app.pilot.authz import PilotAuthContext, PilotRole


class AuthProvider(Protocol):
    def verify_request(self, headers: Mapping[str, str | None]) -> PilotAuthContext:
        """Verify request auth material and return the route auth context."""
        ...


class PilotAuthProviderError(ValueError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PilotHeaderAuthProvider:
    """Development-only auth provider backed by explicit pilot headers."""

    actor_user_id_header = "x-pilot-actor-user-id"
    organization_id_header = "x-pilot-organization-id"
    roles_header = "x-pilot-roles"
    request_id_header = "x-pilot-request-id"

    def verify_request(self, headers: Mapping[str, str | None]) -> PilotAuthContext:
        actor_user_id = _header_value(headers, self.actor_user_id_header)
        organization_id = _header_value(headers, self.organization_id_header)
        role_values = _header_value(headers, self.roles_header)
        request_id = _header_value(headers, self.request_id_header)

        if not actor_user_id or not organization_id or not role_values:
            raise PilotAuthProviderError(
                code="missing_auth_context",
                message="Pilot auth context headers are required.",
            )

        try:
            roles = frozenset(PilotRole(role.strip()) for role in role_values.split(",") if role.strip())
            if not roles:
                raise ValueError("At least one role is required.")
            return PilotAuthContext(
                actor_user_id=uuid.UUID(actor_user_id),
                organization_id=uuid.UUID(organization_id),
                roles=roles,
                request_id=request_id,
            )
        except ValueError as exc:
            raise PilotAuthProviderError(code="invalid_auth_context", message=str(exc)) from exc


def _header_value(headers: Mapping[str, str | None], name: str) -> str | None:
    return headers.get(name) or headers.get(name.lower()) or headers.get(_canonical_header_name(name))


def _canonical_header_name(name: str) -> str:
    return "-".join(part.capitalize() for part in name.split("-"))
