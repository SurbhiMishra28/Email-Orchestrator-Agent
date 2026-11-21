"""Tenant and team management API (admin-only).

Membership is the ``TenantMember`` table, which already existed but was unused.
Every route here resolves the caller's own tenant, so an admin can only ever
manage their own team. The last admin of a tenant cannot be demoted or removed:
that would leave the tenant with nobody able to administer it.
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.auth import UserPayload, hash_password, require_role
from app.db import SessionLocal, Tenant, TenantMember, User
from app.deps import current_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_ROLES = {"admin", "member", "user"}


class TenantOut(BaseModel):
    id: int
    name: str
    plan: str
    daily_email_limit: int
    member_count: int


class MemberOut(BaseModel):
    id: int
    user_id: int
    email: str
    name: Optional[str] = None
    role: str
    is_active: bool
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None


class MemberInvite(BaseModel):
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=255)
    role: str = "member"


class MemberUpdate(BaseModel):
    role: str


def _admin_count(db, tenant_id: int) -> int:
    return (
        db.query(TenantMember)
        .filter(TenantMember.tenant_id == tenant_id, TenantMember.role == "admin")
        .count()
    )


def _get_member(db, tenant_id: int, member_id: int) -> TenantMember:
    member = (
        db.query(TenantMember)
        .filter(TenantMember.id == member_id, TenantMember.tenant_id == tenant_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.get("", response_model=TenantOut)
def get_tenant(
    tenant_id: int = Depends(current_tenant_id),
    user: UserPayload = Depends(require_role("admin")),
):
    """Return the caller's tenant summary."""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return TenantOut(
            id=tenant.id,
            name=tenant.name,
            plan=tenant.plan,
            daily_email_limit=tenant.daily_email_limit,
            member_count=db.query(TenantMember)
            .filter(TenantMember.tenant_id == tenant_id)
            .count(),
        )
    finally:
        db.close()


@router.get("/members", response_model=List[MemberOut])
def list_members(
    tenant_id: int = Depends(current_tenant_id),
    user: UserPayload = Depends(require_role("admin")),
):
    """List every member of the caller's tenant."""
    db = SessionLocal()
    try:
        rows = (
            db.query(TenantMember, User)
            .join(User, TenantMember.user_id == User.id)
            .filter(TenantMember.tenant_id == tenant_id)
            .order_by(TenantMember.id.asc())
            .all()
        )
        return [
            MemberOut(
                id=member.id,
                user_id=member.user_id,
                email=account.email,
                name=account.name,
                role=member.role,
                is_active=account.is_active,
                invited_at=member.invited_at,
                accepted_at=member.accepted_at,
            )
            for member, account in rows
        ]
    finally:
        db.close()


@router.post("/members", response_model=dict, status_code=201)
def invite_member(
    payload: MemberInvite,
    tenant_id: int = Depends(current_tenant_id),
    user: UserPayload = Depends(require_role("admin")),
):
    """Add a teammate to the tenant.

    There is no mail delivery in the product yet, so the account is created
    with a generated temporary password which is returned exactly once for the
    admin to pass on. An existing account is attached instead of duplicated.
    """
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of {sorted(VALID_ROLES)}")

    db = SessionLocal()
    try:
        account = db.query(User).filter(User.email == payload.email).first()
        temporary_password = None

        if account is not None:
            if account.tenant_id != tenant_id:
                raise HTTPException(
                    status_code=409,
                    detail="That email already belongs to another workspace.",
                )
            existing = (
                db.query(TenantMember)
                .filter(
                    TenantMember.tenant_id == tenant_id,
                    TenantMember.user_id == account.id,
                )
                .first()
            )
            if existing is not None:
                raise HTTPException(status_code=409, detail="That person is already a member.")
            account_id = account.id
        else:
            temporary_password = secrets.token_urlsafe(12)
            account = User(
                tenant_id=tenant_id,
                email=payload.email,
                hashed_password=hash_password(temporary_password),
                name=payload.name or payload.email.split("@")[0],
                role=payload.role,
            )
            db.add(account)
            db.flush()
            account_id = account.id

        member = TenantMember(
            user_id=account_id,
            tenant_id=tenant_id,
            role=payload.role,
            invited_at=datetime.now(timezone.utc),
        )
        db.add(member)
        db.commit()
        db.refresh(member)

        logger.info("Invited %s to tenant %s as %s", payload.email, tenant_id, payload.role)
        return {
            "id": member.id,
            "user_id": account_id,
            "email": payload.email,
            "role": member.role,
            "temporary_password": temporary_password,
        }
    finally:
        db.close()


@router.patch("/members/{member_id}", response_model=MemberOut)
def update_member_role(
    member_id: int,
    payload: MemberUpdate,
    tenant_id: int = Depends(current_tenant_id),
    user: UserPayload = Depends(require_role("admin")),
):
    """Change a member's role without leaving the tenant unadministered."""
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of {sorted(VALID_ROLES)}")

    db = SessionLocal()
    try:
        member = _get_member(db, tenant_id, member_id)

        if member.role == "admin" and payload.role != "admin" and _admin_count(db, tenant_id) <= 1:
            raise HTTPException(
                status_code=409,
                detail="The workspace needs at least one admin.",
            )

        member.role = payload.role
        account = db.query(User).filter(User.id == member.user_id).first()
        if account is not None:
            account.role = payload.role
        db.commit()
        db.refresh(member)

        return MemberOut(
            id=member.id,
            user_id=member.user_id,
            email=account.email if account else "",
            name=account.name if account else None,
            role=member.role,
            is_active=account.is_active if account else False,
            invited_at=member.invited_at,
            accepted_at=member.accepted_at,
        )
    finally:
        db.close()


@router.delete("/members/{member_id}")
def remove_member(
    member_id: int,
    tenant_id: int = Depends(current_tenant_id),
    user: UserPayload = Depends(require_role("admin")),
):
    """Remove a member from the workspace, guarding the last admin."""
    db = SessionLocal()
    try:
        member = _get_member(db, tenant_id, member_id)

        if member.role == "admin" and _admin_count(db, tenant_id) <= 1:
            raise HTTPException(
                status_code=409,
                detail="The workspace needs at least one admin.",
            )
        if member.user_id == user.id:
            raise HTTPException(
                status_code=409,
                detail="You cannot remove your own membership. Ask another admin.",
            )

        db.delete(member)
        db.commit()
        return {"message": "Member removed"}
    finally:
        db.close()
