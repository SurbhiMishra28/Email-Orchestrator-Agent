"""Authentication routes for SaaS multi-tenant system."""
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, EmailStr, Field, SecretStr

from app.auth import (
    create_access_token,
    verify_password,
    hash_password,
    generate_api_key,
    get_current_user,
    UserPayload,
)
from app.db import SessionLocal, User, APIKey, Tenant, TenantMember

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Request/Response Models ============

class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(max_length=255)
    tenant_name: str = Field(max_length=255)


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"


class APIKeyCreate(BaseModel):
    """API key creation request."""
    name: str = Field(max_length=255, default="API Key")
    permissions: List[str] = Field(default_factory=list)


class APIKeyResponse(BaseModel):
    """API key response model."""
    id: int
    name: str
    key: str  # Only shown once
    permissions: List[str]
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True



# ============ Registration Endpoint ============

@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserRegister):
    """
    Register a new user and create their tenant.
    
    Returns JWT token for immediate API access.
    """
    db = SessionLocal()
    try:
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Check if tenant name is taken
        existing_tenant = db.query(Tenant).filter(Tenant.name == user_data.tenant_name).first()
        if existing_tenant:
            raise HTTPException(status_code=400, detail="Tenant name already exists")
        
        # Create tenant
        tenant = Tenant(name=user_data.tenant_name)
        db.add(tenant)
        db.flush()  # Get tenant ID
        
        # Create user
        hashed_password = hash_password(user_data.password)
        user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            name=user_data.name,
            tenant_id=tenant.id,
            role="admin"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Track the creator as the tenant's first admin member.
        db.add(
            TenantMember(
                user_id=user.id,
                tenant_id=tenant.id,
                role="admin",
                accepted_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        # Provision per-tenant settings, SMTP and starter templates so a new
        # account has a working workspace immediately. Inheritance defaults to
        # on, which is right for this single-workspace build: the deployment's
        # environment is the mailbox this app sends from.
        from app.services.provisioning import provision_tenant_defaults

        provision_tenant_defaults(db, tenant.id)

        # Create access token with 7-day expiry. The tenant claim lets the rate
        # limiter key on the tenant instead of a shared IP address.
        access_token = create_access_token(
            data={"sub": user.id, "tenant_id": tenant.id},
            expires_delta=timedelta(days=7)
        )
        
        logger.info(f"New user registered: {user_data.email} (tenant: {user_data.tenant_name})")
        
        return {"access_token": access_token}
    
    except HTTPException:
        # Preserve 400/409 validation responses instead of masking them as 500.
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Registration failed: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")
    finally:
        db.close()


# ============ Login Endpoint ============

@router.post("/login", response_model=TokenResponse)
async def login(login_data: UserLogin):
    """
    Authenticate user and return JWT token.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == login_data.email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        if not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")
        
        # Create access token
        access_token = create_access_token(
            data={"sub": user.id, "tenant_id": user.tenant_id},
            expires_delta=timedelta(days=7)
        )
        
        logger.info(f"User logged in: {user.email}")
        return {"access_token": access_token}
    
    finally:
        db.close()


# ============ Current User Endpoint ============

@router.get("/me")
async def get_current_user_info(user: UserPayload = Depends(get_current_user)):
    """
    Get the current authenticated user's information.
    """
    db = SessionLocal()
    try:
        user_row = db.query(User).filter(User.id == user.id).first()
        if user_row is None:
            raise HTTPException(status_code=404, detail="User not found")
        tenant = db.query(Tenant).filter(Tenant.id == user_row.tenant_id).first()

        return {
            "id": user_row.id,
            "email": user_row.email,
            "name": user_row.name,
            "role": user_row.role,
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "plan": tenant.plan,
                "daily_email_limit": tenant.daily_email_limit
            }
        }
    finally:
        db.close()


# ============ API Key Endpoints ============

@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    api_key_data: APIKeyCreate,
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Create a new API key for the authenticated user.
    
    API keys are used for programmatic access instead of password authentication.
    """
    db = SessionLocal()
    try:
        # Check API key limit for tenant
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        api_key_count = db.query(APIKey).filter(
            APIKey.user_id == current_user.id,
            APIKey.is_active == True
        ).count()
        
        if api_key_count >= tenant.api_key_limit:
            raise HTTPException(
                status_code=400,
                detail=f"API key limit ({tenant.api_key_limit}) reached for this tenant"
            )
        
        # Generate secure API key
        key_value = generate_api_key()
        
        api_key = APIKey(
            user_id=current_user.id,
            name=api_key_data.name,
            key=key_value,
            permissions=api_key_data.permissions
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        
        logger.info(f"API key created for user {current_user.email}: {api_key_data.name}")
        
        return {
            "id": api_key.id,
            "name": api_key.name,
            "key": api_key.key,  # Only shown once!
            "permissions": api_key.permissions,
            "is_active": api_key.is_active,
            "created_at": api_key.created_at
        }
    finally:
        db.close()


@router.get("/api-keys", response_model=List[APIKeyResponse])
async def list_api_keys(current_user: UserPayload = Depends(get_current_user)):
    """
    List all active API keys for the authenticated user.
    """
    db = SessionLocal()
    try:
        api_keys = db.query(APIKey).filter(
            APIKey.user_id == current_user.id
        ).all()
        
        return api_keys
    finally:
        db.close()


@router.delete("/api-keys/{api_key_id}")
async def revoke_api_key(
    api_key_id: int,
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Revoke (disable) an API key.
    """
    db = SessionLocal()
    try:
        api_key = db.query(APIKey).filter(
            APIKey.id == api_key_id,
            APIKey.user_id == current_user.id
        ).first()
        
        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")
        
        api_key.is_active = False
        db.commit()
        
        logger.info(f"API key revoked: {api_key.name} for user {current_user.email}")
        return {"message": "API key revoked successfully"}
    finally:
        db.close()


@router.post("/refresh-token", response_model=TokenResponse)
async def refresh_token(current_user: UserPayload = Depends(get_current_user)):
    """Issue a fresh access token for a still-valid one.

    Full refresh-token rotation with a separate long-lived token and revocation
    list is a larger change; this keeps sessions alive without forcing a
    re-login while the current token is valid.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == current_user.id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        access_token = create_access_token(
            data={"sub": user.id, "tenant_id": user.tenant_id},
            expires_delta=timedelta(days=7),
        )
        return {"access_token": access_token}
    finally:
        db.close()