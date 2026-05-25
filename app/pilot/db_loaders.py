from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import SubjectPack
from app.db.services.subject_packs import resolve_active_subject_pack
from app.pilot.authz import (
    PilotAuthContext,
    PilotPermission,
    TenantScopedResource,
    authorize_tenant_resource,
    require_permission,
)


def load_subject_pack_for_context(
    db: Session,
    *,
    key: str,
    context: PilotAuthContext,
    allow_global: bool = True,
) -> SubjectPack | None:
    require_permission(context, PilotPermission.READ_SUBJECT_PACKS)
    pack = resolve_active_subject_pack(
        db,
        key=key,
        organization_id=context.organization_id,
        allow_global=allow_global,
    )
    if pack is None:
        return None
    if pack.organization_id is None:
        return pack

    authorize_tenant_resource(
        context=context,
        resource=TenantScopedResource(
            organization_id=pack.organization_id,
            resource_type="subject_pack",
            resource_id=pack.id,
        ),
        permission=PilotPermission.READ_SUBJECT_PACKS,
    )
    return pack
