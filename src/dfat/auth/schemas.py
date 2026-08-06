"""Pydantic request/response schemas for authentication APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Credentials for investigator login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Bearer token pair returned after successful authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """Refresh-token exchange request."""

    refresh_token: str


class RegisterRequest(BaseModel):
    """New investigator account registration request."""

    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12)
    full_name: str = Field(min_length=1)
    role_name: str = "analyst"


class UserResponse(BaseModel):
    """Public user profile response."""

    id: str
    username: str
    email: str
    full_name: str
    role_name: str
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime


class PasswordChangeRequest(BaseModel):
    """Authenticated password change request."""

    current_password: str
    new_password: str = Field(min_length=12)


class TokenPayload(BaseModel):
    """Decoded JWT access-token payload."""

    sub: str
    username: str
    role: str
    type: str
    jti: str
    exp: int
    iat: int
