"""Authentication API routes (register, login, token lifecycle)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from dfat.api.dependencies import (
    get_current_active_user,
    get_jwt_handler,
    get_user_service,
    oauth2_scheme,
    require_role,
)
from dfat.auth.jwt_handler import JWTHandler
from dfat.auth.schemas import (
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from dfat.database.models.user import UserORM
from dfat.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Auth"])


def _client_meta(request: Request) -> tuple[str, str]:
    """Extract client IP and user-agent for session audit metadata."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip_address = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        ip_address = request.client.host
    else:
        ip_address = "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    return ip_address, user_agent


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    body: RegisterRequest,
    current_user: UserORM = Depends(require_role(["admin", "investigator"])),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Register a new investigator account (admin/investigator only)."""
    return await user_service.register_user(body, registered_by=current_user.id)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """Authenticate with username/password and issue a token pair."""
    ip_address, user_agent = _client_meta(request)
    return await user_service.authenticate(
        form_data.username,
        form_data.password,
        ip_address,
        user_agent,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    body: RefreshRequest,
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """Exchange a refresh token for a new access/refresh pair."""
    return await user_service.refresh_token(body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user: UserORM = Depends(get_current_active_user),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
    user_service: UserService = Depends(get_user_service),
) -> None:
    """Revoke the current access-token session."""
    claims: dict[str, Any] = jwt_handler.decode_token(token)
    await user_service.logout(str(claims["jti"]), current_user.id)


@router.post("/logout-all", status_code=status.HTTP_200_OK)
async def logout_all(
    current_user: UserORM = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> dict[str, int]:
    """Revoke all sessions for the authenticated user."""
    count = await user_service.logout_all(current_user.id)
    return {"revoked_count": count}


@router.put("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeRequest,
    current_user: UserORM = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> None:
    """Change the authenticated user's password."""
    await user_service.change_password(
        current_user.id,
        body.current_password,
        body.new_password,
    )
