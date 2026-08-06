"""Unit tests for UserService business logic with mocked repositories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.auth.exceptions import (
    AccountLockedError,
    AuthenticationError,
    InvalidCredentialsError,
)
from dfat.auth.password import PasswordHasher
from dfat.auth.schemas import RegisterRequest
from dfat.auth.jwt_handler import JWTHandler
from dfat.services.user_service import UserService
from dfat.settings import AuthSettings
from tests.conftest import TEST_JWT_SECRET


def _service(
    *,
    user_repo: AsyncMock | None = None,
    session_repo: AsyncMock | None = None,
    hasher: PasswordHasher | None = None,
    jwt: JWTHandler | None = None,
    audit_repo: AsyncMock | None = None,
    settings: AuthSettings | None = None,
) -> UserService:
    return UserService(
        user_repo=user_repo or AsyncMock(),
        session_repo=session_repo or AsyncMock(),
        password_hasher=hasher or PasswordHasher(),
        jwt_handler=jwt
        or JWTHandler(secret_key=TEST_JWT_SECRET, access_token_expire_minutes=60),
        audit_repo=audit_repo
        or AsyncMock(get_latest_entry_number=AsyncMock(return_value=0)),
        auth_settings=settings
        or AuthSettings(secret_key=TEST_JWT_SECRET, max_login_attempts=5),
    )


@pytest.mark.asyncio
async def test_register_user_success() -> None:
    """Successful registration hashes the password and persists the user."""
    # Arrange
    user_repo = AsyncMock()
    user_repo.get_by_username.return_value = None
    user_repo.get_by_email.return_value = None
    role = MagicMock()
    role.id = "role-analyst"
    role.name = "analyst"
    user_repo.get_role_by_name.return_value = role
    saved: list = []

    async def save(user):  # type: ignore[no-untyped-def]
        saved.append(user)
        return user.id

    user_repo.save.side_effect = save

    async def get(uid):  # type: ignore[no-untyped-def]
        loaded = MagicMock()
        loaded.id = saved[0].id
        loaded.username = "alice"
        loaded.email = "a@example.com"
        loaded.full_name = "Alice"
        loaded.is_active = True
        loaded.is_locked = False
        loaded.failed_login_attempts = 0
        loaded.last_login = None
        loaded.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        loaded.role = role
        return loaded

    user_repo.get.side_effect = get
    hasher = PasswordHasher()
    service = _service(user_repo=user_repo, hasher=hasher)

    # Act
    response = await service.register_user(
        RegisterRequest(
            username="alice",
            email="a@example.com",
            password="C0mpl3x!Pass#123",
            full_name="Alice",
        )
    )

    # Assert
    assert response.username == "alice"
    assert saved
    assert hasher.verify_password("C0mpl3x!Pass#123", saved[0].hashed_password)


@pytest.mark.asyncio
async def test_register_user_duplicate_username() -> None:
    """Duplicate usernames raise AuthenticationError."""
    # Arrange
    user_repo = AsyncMock()
    user_repo.get_by_username.return_value = MagicMock()
    service = _service(user_repo=user_repo)

    # Act / Assert
    with pytest.raises(AuthenticationError, match="Username already exists"):
        await service.register_user(
            RegisterRequest(
                username="alice",
                email="a@example.com",
                password="C0mpl3x!Pass#123",
                full_name="Alice",
            )
        )


@pytest.mark.asyncio
async def test_authenticate_success() -> None:
    """Valid credentials return a token pair and reset failed attempts."""
    # Arrange
    hasher = PasswordHasher()
    user = MagicMock()
    user.id = "user-1"
    user.username = "alice"
    user.is_active = True
    user.is_locked = False
    user.locked_until = None
    user.hashed_password = hasher.hash_password("C0mpl3x!Pass#123")
    user.role = MagicMock(name="analyst")
    user.role.name = "analyst"
    user_repo = AsyncMock()
    user_repo.get_by_username.return_value = user
    session_repo = AsyncMock()
    service = _service(user_repo=user_repo, session_repo=session_repo, hasher=hasher)

    # Act
    tokens = await service.authenticate("alice", "C0mpl3x!Pass#123", "127.0.0.1", "ua")

    # Assert
    assert tokens.access_token
    assert tokens.refresh_token
    user_repo.reset_failed_attempts.assert_awaited()
    session_repo.create_session.assert_awaited()


@pytest.mark.asyncio
async def test_authenticate_wrong_password() -> None:
    """Wrong passwords increment failed attempts."""
    # Arrange
    hasher = PasswordHasher()
    user = MagicMock()
    user.id = "user-1"
    user.username = "alice"
    user.is_active = True
    user.is_locked = False
    user.locked_until = None
    user.hashed_password = hasher.hash_password("C0mpl3x!Pass#123")
    user.failed_login_attempts = 1
    user.role = MagicMock()
    user.role.name = "analyst"
    user_repo = AsyncMock()
    user_repo.get_by_username.return_value = user
    user_repo.get.return_value = user
    service = _service(user_repo=user_repo, hasher=hasher)

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate("alice", "wrong-password!", "127.0.0.1", "ua")
    user_repo.increment_failed_attempts.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
async def test_authenticate_locked_account() -> None:
    """Locked accounts raise AccountLockedError before password checks."""
    # Arrange
    user = MagicMock()
    user.id = "user-1"
    user.username = "alice"
    user.is_active = True
    user.is_locked = True
    user.locked_until = datetime.now(UTC) + timedelta(minutes=30)
    user_repo = AsyncMock()
    user_repo.get_by_username.return_value = user
    service = _service(user_repo=user_repo)

    # Act / Assert
    with pytest.raises(AccountLockedError):
        await service.authenticate("alice", "anything", "127.0.0.1", "ua")


@pytest.mark.asyncio
async def test_change_password_success() -> None:
    """Change password succeeds when the current password matches."""
    # Arrange
    hasher = PasswordHasher()
    user = MagicMock()
    user.id = "user-1"
    user.hashed_password = hasher.hash_password("OldPass123!@#")
    user_repo = AsyncMock()
    user_repo.get.return_value = user
    session_repo = AsyncMock()
    service = _service(user_repo=user_repo, session_repo=session_repo, hasher=hasher)

    # Act
    await service.change_password("user-1", "OldPass123!@#", "NewPass123!@#")

    # Assert
    assert hasher.verify_password("NewPass123!@#", user.hashed_password)
    user_repo.save.assert_awaited()
    session_repo.revoke_all_user_sessions.assert_awaited_with("user-1")


@pytest.mark.asyncio
async def test_change_password_wrong_current() -> None:
    """Wrong current password raises InvalidCredentialsError."""
    # Arrange
    hasher = PasswordHasher()
    user = MagicMock()
    user.id = "user-1"
    user.hashed_password = hasher.hash_password("OldPass123!@#")
    user_repo = AsyncMock()
    user_repo.get.return_value = user
    service = _service(user_repo=user_repo, hasher=hasher)

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await service.change_password("user-1", "WrongPass123!", "NewPass123!@#")


@pytest.mark.asyncio
async def test_logout_and_list_helpers() -> None:
    """Logout helpers and user listing call the expected repositories."""
    # Arrange
    user_repo = AsyncMock()
    role = MagicMock()
    role.name = "analyst"
    user = MagicMock()
    user.id = "user-1"
    user.username = "alice"
    user.email = "a@example.com"
    user.full_name = "Alice"
    user.is_active = True
    user.last_login = None
    user.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    user.role = role
    user_repo.get.return_value = user
    user_repo.list_all.return_value = [user]
    session_repo = AsyncMock()
    session_repo.revoke_all_user_sessions.return_value = 2
    service = _service(user_repo=user_repo, session_repo=session_repo)

    # Act
    await service.logout("jti-1", "user-1")
    count = await service.logout_all("user-1")
    profile = await service.get_user("user-1")
    users = await service.list_users()
    await service.deactivate_user("user-1", "admin-1")

    # Assert
    assert count == 2
    assert profile.username == "alice"
    assert len(users) == 1
    session_repo.revoke_session.assert_awaited_with("jti-1")
    user_repo.save.assert_awaited()


@pytest.mark.asyncio
async def test_refresh_token_success() -> None:
    """Refresh exchanges a valid refresh token for a new pair."""
    # Arrange
    jwt = JWTHandler(secret_key=TEST_JWT_SECRET)
    _access, refresh, jti = jwt.create_token_pair("user-1", "alice", "analyst")
    role = MagicMock()
    role.name = "analyst"
    user = MagicMock()
    user.id = "user-1"
    user.username = "alice"
    user.is_active = True
    user.role = role
    user_repo = AsyncMock()
    user_repo.get.return_value = user
    session_repo = AsyncMock()
    session_repo.is_token_revoked.return_value = False
    service = _service(user_repo=user_repo, session_repo=session_repo, jwt=jwt)

    # Act
    tokens = await service.refresh_token(refresh)

    # Assert
    assert tokens.access_token
    assert tokens.refresh_token
    session_repo.revoke_session.assert_awaited_with(jti)
    session_repo.create_session.assert_awaited()
