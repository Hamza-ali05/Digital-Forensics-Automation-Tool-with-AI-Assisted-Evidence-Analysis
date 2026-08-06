"""User profile and administration API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dfat.api.dependencies import (
    get_current_active_user,
    get_user_service,
    require_role,
)
from dfat.auth.schemas import UserResponse
from dfat.database.models.user import UserORM
from dfat.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: UserORM = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Return the authenticated user's public profile."""
    return await user_service.get_user(current_user.id)


@router.get("", response_model=list[UserResponse])
async def list_users(
    _: UserORM = Depends(require_role(["admin"])),
    user_service: UserService = Depends(get_user_service),
) -> list[UserResponse]:
    """List all users (admin only)."""
    return await user_service.list_users()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    _: UserORM = Depends(require_role(["admin"])),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Get a user profile by ID (admin only)."""
    return await user_service.get_user(user_id)


@router.put("/{user_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    current_user: UserORM = Depends(require_role(["admin"])),
    user_service: UserService = Depends(get_user_service),
) -> None:
    """Deactivate a user account (admin only)."""
    await user_service.deactivate_user(user_id, current_user.id)
