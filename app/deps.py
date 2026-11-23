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
]


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
