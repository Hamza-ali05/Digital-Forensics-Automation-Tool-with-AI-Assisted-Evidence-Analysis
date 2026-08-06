"""FastAPI authentication and authorisation dependencies."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dfat.auth.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    AuthenticationError,
    TokenInvalidError,
    TokenRevokedError,
)
from dfat.auth.jwt_handler import JWTHandler
from dfat.database.models.user import UserORM
from dfat.database.repositories.session_repo import SessionRepository
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


def _container(request: Request):  # type: ignore[no-untyped-def]
    """Return the application DI container from request state."""
    return request.app.state.container


def get_jwt_handler(request: Request) -> JWTHandler:
    """Resolve the JWT handler from the DI container."""
    return _container(request).auth.jwt_handler()


def get_session_repo(request: Request) -> SessionRepository:
    """Resolve the session repository from the DI container."""
    return _container(request).repositories.session_repo()


def get_user_repo(request: Request) -> SQLAlchemyUserRepository:
    """Resolve the user repository from the DI container."""
    return _container(request).repositories.user_repo()


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
    session_repo: SessionRepository = Depends(get_session_repo),
    user_repo: SQLAlchemyUserRepository = Depends(get_user_repo),
) -> UserORM:
    """Authenticate the caller and return the active ``UserORM``.

    Steps:
        1. Decode the JWT access token.
        2. Reject revoked JTIs.
        3. Load the user (with role) from persistence.
        4. Reject disabled or locked accounts.

    Args:
        request: Incoming HTTP request (for DI container access).
        token: Bearer access token.
        jwt_handler: JWT codec.
        session_repo: Session revocation repository.
        user_repo: User repository.

    Returns:
        Authenticated user ORM instance.

    Raises:
        TokenInvalidError: If the token type/claims are invalid.
        TokenRevokedError: If the session JTI has been revoked.
        AuthenticationError: If the user cannot be loaded.
        AccountDisabledError: If the account is inactive.
        AccountLockedError: If the account is locked.
    """
    _ = request
    claims = jwt_handler.decode_token(token)
    if claims.get("type") != "access":
        raise TokenInvalidError(
            "Access token required",
            context={"token_type": claims.get("type")},
        )
    jti = claims.get("jti")
    if not jti:
        raise TokenInvalidError("Token missing jti claim")
    if await session_repo.is_token_revoked(str(jti)):
        raise TokenRevokedError(
            "Token has been revoked",
            context={"jti": str(jti)},
        )

    user_id = str(claims.get("sub", ""))
    user = await _load_user_with_role(user_repo, user_id)
    if user is None:
        raise AuthenticationError(
            "Authenticated user not found",
            context={"user_id": user_id},
        )
    if not user.is_active:
        raise AccountDisabledError(
            "Account is disabled",
            context={"user_id": user_id},
        )
    if user.is_locked:
        locked_until = user.locked_until
        now = datetime.now(UTC)
        if locked_until is not None and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if locked_until is None or locked_until > now:
            raise AccountLockedError(
                locked_until=locked_until,
                context={"user_id": user_id},
            )
    return user


async def get_current_active_user(
    current_user: UserORM = Depends(get_current_user),
) -> UserORM:
    """Return the current user after confirming ``is_active``.

    Args:
        current_user: Authenticated user from ``get_current_user``.

    Returns:
        Active user ORM instance.

    Raises:
        AccountDisabledError: If the account is inactive.
    """
    if not current_user.is_active:
        raise AccountDisabledError(
            "Account is disabled",
            context={"user_id": current_user.id},
        )
    return current_user


async def get_optional_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme_optional),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
    session_repo: SessionRepository = Depends(get_session_repo),
    user_repo: SQLAlchemyUserRepository = Depends(get_user_repo),
) -> Optional[UserORM]:
    """Return the current user when a valid token is present; otherwise ``None``.

    Args:
        request: Incoming HTTP request.
        token: Optional bearer token.
        jwt_handler: JWT codec.
        session_repo: Session repository.
        user_repo: User repository.

    Returns:
        Authenticated user, or ``None`` when auth is absent/invalid.
    """
    if not token:
        return None
    try:
        return await get_current_user(
            request=request,
            token=token,
            jwt_handler=jwt_handler,
            session_repo=session_repo,
            user_repo=user_repo,
        )
    except AuthenticationError:
        return None


async def _load_user_with_role(
    user_repo: SQLAlchemyUserRepository,
    user_id: str,
) -> Optional[UserORM]:
    """Load a user and eagerly fetch the related role."""
    async with user_repo._session_factory() as session:  # noqa: SLF001
        result = await session.execute(
            select(UserORM)
            .options(selectinload(UserORM.role))
            .where(UserORM.id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none()
