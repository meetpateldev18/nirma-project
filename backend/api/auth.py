"""
Authentication & Authorization API Router — JWT Tokens & RBAC.

This module provides staff user authentication using OAuth2 Password Bearer flow,
bcrypt password hashing, and signed JWT access/refresh tokens.

Endpoints:
    - POST /auth/login: Authenticates user credentials and issues JWT token pair.
    - POST /auth/refresh: Validates refresh token and issues new access token.
    - GET /auth/me: Returns authenticated staff profile.

Dependencies:
    - python-jose >= 3.3
    - passlib[bcrypt] >= 1.7
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.models import StaffUser
from backend.database.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------
class LoginRequest(BaseModel):
    """Payload for user authentication."""
    email: EmailStr = Field(..., example="operator@nirmauni.ac.in")
    password: str = Field(..., min_length=6, example="Admin@Nirma2026")


class TokenResponse(BaseModel):
    """JWT Token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    name: str


class RefreshRequest(BaseModel):
    """Payload for refreshing an access token."""
    refresh_token: str


class StaffUserResponse(BaseModel):
    """Public staff user profile schema."""
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generates a bcrypt cryptographic password hash."""
    return pwd_context.hash(password)


def create_jwt_token(data: dict, expires_delta: timedelta) -> str:
    """Encodes a signed JWT token with an expiration timestamp."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> StaffUser:
    """FastAPI dependency resolving and validating the active JWT Bearer user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id_str: Optional[str] = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    result = await session.execute(select(StaffUser).where(StaffUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def require_admin(current_user: StaffUser = Depends(get_current_user)) -> StaffUser:
    """FastAPI dependency restricting endpoint access to staff members with 'admin' role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires administrator privileges.",
        )
    return current_user


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Authenticates staff user credentials and returns a JWT access and refresh token pair."""
    result = await session.execute(select(StaffUser).where(StaffUser.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        logger.warning("Failed login attempt for email: %s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account disabled")

    access_delta = timedelta(minutes=settings.access_token_expire_minutes)
    refresh_delta = timedelta(days=settings.refresh_token_expire_days)

    access_token = create_jwt_token(data={"sub": str(user.id), "role": user.role}, expires_delta=access_delta)
    refresh_token = create_jwt_token(data={"sub": str(user.id), "type": "refresh"}, expires_delta=refresh_delta)

    logger.info("Successful login for user '%s' (Role: %s)", user.email, user.role)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user.role,
        name=user.name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Validates a refresh token and issues a new access token."""
    try:
        data = jwt.decode(payload.refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if data.get("type") != "refresh":
            raise HTTPException(status_code=400, detail="Invalid token type")
        user_id = int(data["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await session.execute(select(StaffUser).where(StaffUser.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    access_delta = timedelta(minutes=settings.access_token_expire_minutes)
    new_access_token = create_jwt_token(data={"sub": str(user.id), "role": user.role}, expires_delta=access_delta)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=payload.refresh_token,
        role=user.role,
        name=user.name,
    )


@router.get("/me", response_model=StaffUserResponse)
async def get_me(current_user: StaffUser = Depends(get_current_user)) -> StaffUser:
    """Returns profile information for the authenticated staff user."""
    return current_user


# ------------------------------------------------------------------------------
# Admin: Faculty Account Management (accounts are provisioned offline by an admin)
# ------------------------------------------------------------------------------
class UserCreateRequest(BaseModel):
    """Payload for an admin creating a faculty (operator) or admin account."""
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    role: str = Field("operator", pattern="^(admin|operator)$")


class UserUpdateRequest(BaseModel):
    """Payload for an admin enabling/disabling an account or resetting its password."""
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=72)


@router.get("/users", response_model=list[StaffUserResponse])
async def list_users(
    _: StaffUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> list[StaffUser]:
    """Lists every staff account (Admin required)."""
    result = await session.execute(select(StaffUser).order_by(StaffUser.created_at.desc()))
    return list(result.scalars().all())


@router.post("/users", response_model=StaffUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    admin: StaffUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> StaffUser:
    """Grants portal access to a new faculty member (Admin required)."""
    existing = await session.execute(select(StaffUser).where(StaffUser.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = StaffUser(
        email=payload.email,
        name=payload.name.strip(),
        role=payload.role,
        password_hash=get_password_hash(payload.password),
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("Account '%s' (%s) created by admin %s", user.email, user.role, admin.email)
    return user


@router.patch("/users/{user_id}", response_model=StaffUserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    admin: StaffUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> StaffUser:
    """Enables/disables an account or resets its password (Admin required)."""
    result = await session.execute(select(StaffUser).where(StaffUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account.")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password:
        user.password_hash = get_password_hash(payload.password)
    await session.commit()
    await session.refresh(user)
    logger.info("Account '%s' updated by admin %s", user.email, admin.email)
    return user
