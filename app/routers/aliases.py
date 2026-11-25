"""Sender aliases (Brevo's "senders").

An alias is a From identity: the address recipients see plus the display name.
Tenants can keep several and pick one per send; the default is used when a send
does not name one.

Nothing here verifies the address. Verification is the mail provider's job (SPF
and DKIM on the domain), and claiming otherwise would be a lie the UI would then
repeat.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError

from app.db import EmailAlias, SessionLocal
from app.deps import current_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter()


class AliasCreate(BaseModel):
    name: str = Field(default="", max_length=255)
    email: EmailStr
    is_default: bool = False


class AliasUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class AliasOut(BaseModel):
    id: int
    name: str
    email: str
    is_default: bool
    is_active: bool

    model_config = {"from_attributes": True}


def _get_alias(db, tenant_id: int, alias_id: int) -> EmailAlias:
    alias = (
        db.query(EmailAlias)
        .filter(EmailAlias.id == alias_id, EmailAlias.tenant_id == tenant_id)
        .first()
    )
    if alias is None:
        raise HTTPException(status_code=404, detail="Alias not found")
    return alias


def _clear_other_defaults(db, tenant_id: int, keep_id: Optional[int] = None) -> None:
    query = db.query(EmailAlias).filter(
        EmailAlias.tenant_id == tenant_id, EmailAlias.is_default.is_(True)
    )
    if keep_id is not None:
        query = query.filter(EmailAlias.id != keep_id)
    for alias in query.all():
        alias.is_default = False


@router.get("", response_model=List[AliasOut])
def list_aliases(tenant_id: int = Depends(current_tenant_id)):
    """Every alias for the caller's workspace, default first."""
    db = SessionLocal()
    try:
        rows = (
            db.query(EmailAlias)
            .filter(EmailAlias.tenant_id == tenant_id)
            .order_by(EmailAlias.is_default.desc(), EmailAlias.id.asc())
            .all()
        )
        return [AliasOut.model_validate(row) for row in rows]
    finally:
        db.close()


@router.post("", response_model=AliasOut, status_code=status.HTTP_201_CREATED)
def create_alias(payload: AliasCreate, tenant_id: int = Depends(current_tenant_id)):
    """Add a sender identity.

    The first alias a workspace creates becomes the default, so sending works
    immediately without a second call.
    """
    db = SessionLocal()
    try:
        existing = db.query(EmailAlias).filter(EmailAlias.tenant_id == tenant_id).count()
        alias = EmailAlias(
            tenant_id=tenant_id,
            name=(payload.name or "").strip(),
            email=str(payload.email).strip().lower(),
            is_default=payload.is_default or existing == 0,
        )
        db.add(alias)
        if alias.is_default:
            _clear_other_defaults(db, tenant_id)
        db.commit()
        db.refresh(alias)
        return AliasOut.model_validate(alias)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That alias already exists for this workspace.",
        )
    finally:
        db.close()


@router.patch("/{alias_id}", response_model=AliasOut)
def update_alias(
    alias_id: int,
    payload: AliasUpdate,
    tenant_id: int = Depends(current_tenant_id),
):
    """Rename, deactivate, or promote an alias to default."""
    db = SessionLocal()
    try:
        alias = _get_alias(db, tenant_id, alias_id)

        if payload.name is not None:
            alias.name = payload.name.strip()
        if payload.email is not None:
            alias.email = str(payload.email).strip().lower()
        if payload.is_active is not None:
            alias.is_active = payload.is_active
        if payload.is_default:
            alias.is_default = True
            _clear_other_defaults(db, tenant_id, keep_id=alias.id)

        db.commit()
        db.refresh(alias)
        return AliasOut.model_validate(alias)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That alias already exists for this workspace.",
        )
    finally:
        db.close()


@router.delete("/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alias(alias_id: int, tenant_id: int = Depends(current_tenant_id)):
    """Remove an alias.

    Deleting the default promotes the next remaining alias, so a workspace is
    never left without a sender.
    """
    db = SessionLocal()
    try:
        alias = _get_alias(db, tenant_id, alias_id)
        was_default = alias.is_default
        db.delete(alias)
        db.flush()

        if was_default:
            successor = (
                db.query(EmailAlias)
                .filter(
                    EmailAlias.tenant_id == tenant_id,
                    EmailAlias.is_active.is_(True),
                )
                .order_by(EmailAlias.id.asc())
                .first()
            )
            if successor is not None:
                successor.is_default = True

        db.commit()
    finally:
        db.close()


@router.get("/default", response_model=Optional[AliasOut])
def get_default_alias(tenant_id: int = Depends(current_tenant_id)):
    """The alias used when a send does not name one, or null when none exists."""
    db = SessionLocal()
    try:
        alias = (
            db.query(EmailAlias)
            .filter(
                EmailAlias.tenant_id == tenant_id,
                EmailAlias.is_default.is_(True),
                EmailAlias.is_active.is_(True),
            )
            .first()
        )
        return AliasOut.model_validate(alias) if alias else None
    finally:
        db.close()