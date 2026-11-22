"""Shared FastAPI dependencies for the tenant-scoped API.

Every resource router declares ``Depends(get_current_user)`` and resolves the
caller's tenant through :func:`current_tenant_id`. Filtering reads *and* writes
by that value is what keeps one tenant's data invisible to another.
"""
from fastapi import Depends, HTTPException, status

from app.auth import UserPayload, get_current_user, get_current_user_or_api_key

__all__ = [
    "UserPayload",
    "get_current_user",
    "get_current_user_or_api_key",
    "current_tenant_id",
    "require_tenant",
    "scoped",
    "ensure_sending_allowed",
    "ensure_mailbox_allowed",
    "DEMO_READ_ONLY_DETAIL",
    "DEMO_NO_MAILBOX_DETAIL",
]

DEMO_READ_ONLY_DETAIL = (
    "This is a shared demo workspace: it sends no email and does not store "
    "credentials. Create a free workspace to connect a mailbox."
)

DEMO_NO_MAILBOX_DETAIL = (
    "The shared demo workspace cannot read a mailbox: the inbox connection is "
    "deployment-wide, so syncing here would copy the operator's own mail into a "
    "workspace every visitor can open. Create a free workspace to connect one."
)


def current_tenant_id(user: UserPayload = Depends(get_current_user)) -> int:
    """Return the authenticated caller's tenant id.

    Resource tables allow a NULL ``tenant_id`` for legacy rows, but a request
    without a tenant cannot be scoped, so it is rejected instead of silently
    reading every row.
    """
    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a tenant",
        )
    return int(tenant_id)


def require_tenant(user: UserPayload = Depends(get_current_user)) -> UserPayload:
    """Alias kept for readability when only the payload is needed."""
    return user


def scoped(query, model, tenant_id: int):
    """Apply a tenant filter to a SQLAlchemy query on ``model``."""
    return query.filter(model.tenant_id == tenant_id)


def ensure_sending_allowed(tenant_id: int) -> None:
    """Refuse mail delivery for the shared demo workspace.

    The demo account is handed out in the UI, so anyone can sign into it. By
    default sending is allowed so the demo can demonstrate the product's core
    loop, but on terms that cannot hurt the operator: the demo tenant never
    inherits the deployment's SMTP credentials (``services/provisioning`` only
    copies the environment into the local single-user tenant), so a visitor must
    configure their own relay. The seeded recipients are reserved-domain
    addresses that the placeholder guard refuses, so seeding alone can never
    produce a send either.

    Set ``DEMO_ALLOW_SENDING=false`` to put the workspace back in read-only mode;
    this function then raises 403 for every path that could reach a relay.
    """
    from app.config import settings as app_settings

    if app_settings.DEMO_ALLOW_SENDING:
        return

    from app.db import SessionLocal
    from app.services.demo import is_demo_tenant

    db = SessionLocal()
    try:
        if is_demo_tenant(db, tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=DEMO_READ_ONLY_DETAIL,
            )
    finally:
        db.close()


def ensure_mailbox_allowed(tenant_id: int) -> None:
    """Refuse IMAP access for the shared demo workspace.

    Always refused, whatever ``DEMO_ALLOW_SENDING`` says: the inbox connection is
    deployment-wide (``IMAP_*`` in the environment, not per tenant), so a sync
    from a workspace every visitor can open would copy the operator's private
    mail into it. There is no safe way to enable it without per-tenant mailbox
    credentials.
    """
    from app.db import SessionLocal
    from app.services.demo import is_demo_tenant

    db = SessionLocal()
    try:
        if not is_demo_tenant(db, tenant_id):
            return
    finally:
        db.close()

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=DEMO_NO_MAILBOX_DETAIL,
    )
