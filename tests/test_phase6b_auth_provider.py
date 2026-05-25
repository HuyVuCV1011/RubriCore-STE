import uuid

import pytest

from app.pilot.auth_provider import PilotAuthProviderError, PilotHeaderAuthProvider
from app.pilot.authz import PilotAuthContext, PilotRole


def pilot_headers(
    *,
    actor_user_id: uuid.UUID | str | None = None,
    organization_id: uuid.UUID | str | None = None,
    roles: str | None = "teacher,read_only",
    request_id: str | None = "phase6b-test",
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if actor_user_id is not None:
        headers["X-Pilot-Actor-User-Id"] = str(actor_user_id)
    if organization_id is not None:
        headers["X-Pilot-Organization-Id"] = str(organization_id)
    if roles is not None:
        headers["X-Pilot-Roles"] = roles
    if request_id is not None:
        headers["X-Pilot-Request-Id"] = request_id
    return headers


def test_pilot_header_auth_provider_returns_context_for_valid_headers() -> None:
    actor_user_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    provider = PilotHeaderAuthProvider()

    context = provider.verify_request(
        pilot_headers(actor_user_id=actor_user_id, organization_id=organization_id)
    )

    assert isinstance(context, PilotAuthContext)
    assert context.actor_user_id == actor_user_id
    assert context.organization_id == organization_id
    assert context.roles == frozenset({PilotRole.TEACHER, PilotRole.READ_ONLY})
    assert context.request_id == "phase6b-test"


@pytest.mark.parametrize(
    "headers",
    [
        pilot_headers(organization_id=uuid.uuid4()),
        pilot_headers(actor_user_id=uuid.uuid4()),
        pilot_headers(actor_user_id=uuid.uuid4(), organization_id=uuid.uuid4(), roles=None),
    ],
)
def test_pilot_header_auth_provider_rejects_missing_headers(headers: dict[str, str]) -> None:
    provider = PilotHeaderAuthProvider()

    with pytest.raises(PilotAuthProviderError) as exc_info:
        provider.verify_request(headers)

    assert exc_info.value.code == "missing_auth_context"


def test_pilot_header_auth_provider_requires_at_least_one_role() -> None:
    provider = PilotHeaderAuthProvider()

    with pytest.raises(PilotAuthProviderError) as exc_info:
        provider.verify_request(
            pilot_headers(actor_user_id=uuid.uuid4(), organization_id=uuid.uuid4(), roles=" , ")
        )

    assert exc_info.value.code == "invalid_auth_context"
    assert "At least one role is required" in exc_info.value.message


@pytest.mark.parametrize(
    ("actor_user_id", "organization_id"),
    [
        ("not-a-uuid", uuid.uuid4()),
        (uuid.uuid4(), "not-a-uuid"),
    ],
)
def test_pilot_header_auth_provider_rejects_malformed_uuids(
    actor_user_id: uuid.UUID | str,
    organization_id: uuid.UUID | str,
) -> None:
    provider = PilotHeaderAuthProvider()

    with pytest.raises(PilotAuthProviderError) as exc_info:
        provider.verify_request(
            pilot_headers(actor_user_id=actor_user_id, organization_id=organization_id)
        )

    assert exc_info.value.code == "invalid_auth_context"


def test_pilot_header_auth_provider_rejects_unknown_roles() -> None:
    provider = PilotHeaderAuthProvider()

    with pytest.raises(PilotAuthProviderError) as exc_info:
        provider.verify_request(
            pilot_headers(actor_user_id=uuid.uuid4(), organization_id=uuid.uuid4(), roles="teacher,owner")
        )

    assert exc_info.value.code == "invalid_auth_context"
    assert "owner" in exc_info.value.message
