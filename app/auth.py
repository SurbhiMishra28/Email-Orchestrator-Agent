"""Authentication and Authorization for SaaS Multi-Tenant System.

This module provides:
- JWT-based authentication
- Multi-tenant organization support
- Role-based access control
- API key management for programmatic access
"""
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Callable
from functools import wraps
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.db import (
    APIKey as APIKeyModel,
    SessionLocal,
    Tenant,
    TenantMember,
    User,
)

logger = logging.getLogger(__name__)

# bcrypt only uses the first 72 bytes and raises on longer input, so truncate.
BCRYPT_MAX_BYTES = 72


def _password_bytes(password: str) -> bytes:
    return (password or "").encode("utf-8")[:BCRYPT_MAX_BYTES]


# JWT settings. A missing JWT_SECRET_KEY must never fall back to a publicly
# known constant, or anyone could forge tokens. Generate an ephemeral secret
# instead: auth works, but tokens do not survive a restart.
SECRET_KEY = settings.JWT_SECRET_KEY or secrets.token_urlsafe(48)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

if not settings.JWT_SECRET_KEY:
    logger.warning(
        "JWT_SECRET_KEY is not set; using an ephemeral secret. "
        "Set JWT_SECRET_KEY in .env so tokens survive restarts."
    )

# Security scheme. ``auto_error=False`` so a missing header reaches our own
# dependency: FastAPI's built-in handler answers 403, but an absent credential
# is an authentication failure (401) and single-user mode needs to see it too.
security = HTTPBearer(auto_error=False)


def get_or_create_local_user() -> "UserPayload":
    """Return the implicit single-user account, creating it on first use.

    Single-user mode runs as a local tool: there is no sign-up flow and no
    bearer token, so every request is attributed to one local tenant.
    """
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
        if tenant is None:
            tenant = Tenant(name=settings.LOCAL_TENANT_NAME, subdomain="local")
            db.add(tenant)
            db.flush()

        user = (
            db.query(User)
            .filter(User.email == settings.LOCAL_USER_EMAIL)
            .first()
        )
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=settings.LOCAL_USER_EMAIL,
                hashed_password=hash_password(secrets.token_urlsafe(24)),
                name=settings.LOCAL_TENANT_NAME,
                role="admin",
            )
            db.add(user)
        db.commit()
        db.refresh(user)
        return UserPayload(
            id=user.id,
            email=user.email,
            tenant_id=tenant.id,
            role=user.role,
            is_api_key=False,
        )
    finally:
        db.close()


# ============ Password Hashing ============

def hash_password(password: str) -> str:
    """Hash a password for storing."""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(
            _password_bytes(plain_password), (hashed_password or "").encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


# ============ JWT Token Management ============

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token.

    python-jose enforces that the ``sub`` claim is a string, so any numeric
    subject is coerced here to keep tokens decodable.
    """
    to_encode = data.copy()
    if "sub" in to_encode and to_encode["sub"] is not None:
        to_encode["sub"] = str(to_encode["sub"])
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> "UserPayload":
    """Resolve the caller.

    With a bearer token the JWT identifies the user. In single-user mode a
    missing token resolves to the implicit local account instead of failing,
    so the bundled dashboard works without a login screen.
    """
    if credentials is None or not credentials.credentials:
        if settings.SINGLE_USER_MODE:
            return get_or_create_local_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        token_data = int(user_id)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == token_data).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        # A token stays valid after the account is deactivated unless it is
        # re-checked here; login() alone would only stop new tokens.
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )
        return UserPayload(
            id=user.id,
            email=user.email,
            tenant_id=user.tenant_id,
            role=user.role,
            is_api_key=False
        )
    finally:
        db.close()


async def get_current_user_or_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> "UserPayload":
    """Get current user from JWT or validate API key."""
    if credentials is None or not credentials.credentials:
        if settings.SINGLE_USER_MODE:
            return get_or_create_local_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is deactivated",
                )
            return UserPayload(
                id=user.id,
                email=user.email,
                tenant_id=user.tenant_id,
                role=user.role,
                is_api_key=False
            )
        finally:
            db.close()
    except JWTError:
        # Try as API key
        api_key = credentials.credentials
        db = SessionLocal()
        try:
            key_record = db.query(APIKeyModel).filter(
                APIKeyModel.key == api_key,
                APIKeyModel.is_active == True
            ).first()
            if key_record is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token or API key")
            
            user = db.query(User).filter(User.id == key_record.user_id).first()
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is deactivated",
                )
            
            return UserPayload(
                id=user.id,
                email=user.email,
                tenant_id=user.tenant_id,
                role=user.role,
                is_api_key=True
            )
        finally:
            db.close()


# ============ Pydantic Models ============

class UserPayload:
    """Payload for authenticated user."""
    def __init__(self, id: int, email: str, tenant_id: int, role: str, is_api_key: bool = False):
        self.id = id
        self.email = email
        self.tenant_id = tenant_id
        self.role = role
        self.is_api_key = is_api_key


class UserCreate(BaseModel):
    """Model for creating a new user."""
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(max_length=255)
    tenant_name: str = Field(max_length=255)


class UserLogin(BaseModel):
    """Model for user login."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Model for token response."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Model for token data."""
    user_id: Optional[int] = None


class APIKeyCreate(BaseModel):
    """Model for API key creation."""
    name: str = Field(max_length=255)
    permissions: List[str] = []


class APIKey(BaseModel):
    """API Key model."""
    id: int
    user_id: int
    name: str
    key: str
    permissions: List[str]
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============ Database Models (SaaS Extensions) ============

# These will be added to db.py
# For now, we'll define the models here for reference


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


# ============ Permission Dependencies ============
#
# These are FastAPI dependencies, not decorators. A decorator cannot receive the
# request's credentials, which is why the previous versions failed. Use them as
# ``Depends(require_role("admin"))``.

def require_tenant_access(user: "UserPayload" = Depends(get_current_user)) -> "UserPayload":
    """Ensure the authenticated user is attached to a tenant."""
    if getattr(user, "tenant_id", None) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a tenant",
        )
    return user


def require_role(*roles: str) -> Callable:
    """Build a dependency that requires one of ``roles``."""

    def dependency(user: "UserPayload" = Depends(get_current_user)) -> "UserPayload":
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return dependency


# ============ User Registration ============

def register_user(user_create: UserCreate) -> tuple:
    """
    Register a new user and create their tenant.
    Returns (user, tenant, token) or raises exception.
    """
    db = SessionLocal()
    try:
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == user_create.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create tenant
        tenant = Tenant(name=user_create.tenant_name)
        db.add(tenant)
        db.flush()  # Get tenant ID
        
        # Create user
        hashed_password = hash_password(user_create.password)
        user = User(
            email=user_create.email,
            hashed_password=hashed_password,
            name=user_create.name,
            tenant_id=tenant.id,
            role="admin"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Add user as tenant member
        tenant_member = TenantMember(
            user_id=user.id,
            tenant_id=tenant.id,
            role="admin"
        )
        db.add(tenant_member)
        db.commit()
        
        # Create access token
        access_token = create_access_token(data={"sub": user.id})
        
        return user, tenant, access_token
    finally:
        db.close()