"""User registration, authentication, and account management services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import uuid4

from dfat.auth.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    AuthenticationError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    RoleNotFoundError,
    TokenInvalidError,
    TokenRevokedError,
)
from dfat.auth.jwt_handler import JWTHandler
from dfat.auth.password import PasswordHasher, validate_password_strength
from dfat.auth.schemas import (
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import AuditEntry
from dfat.database.models.user import UserORM
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.session_repo import SessionRepository
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository
from dfat.settings import AuthSettings


class UserService:
    """Business logic for investigator account lifecycle and authentication."""

    def __init__(
        self,
        user_repo: SQLAlchemyUserRepository,
        session_repo: SessionRepository,
        password_hasher: PasswordHasher,
        jwt_handler: JWTHandler,
        audit_repo: SQLAlchemyAuditRepository,
        auth_settings: AuthSettings,
    ) -> None:
        """Initialise the user service.

        Args:
            user_repo: User persistence repository.
            session_repo: JWT session repository.
            password_hasher: Password hashing utility.
            jwt_handler: JWT token utility.
            audit_repo: Database audit repository.
            auth_settings: Authentication settings.
        """
        self._user_repo = user_repo
        self._session_repo = session_repo
        self._password_hasher = password_hasher
        self._jwt_handler = jwt_handler
        self._audit_repo = audit_repo
        self._auth_settings = auth_settings

    async def register_user(
        self,
        request: RegisterRequest,
        registered_by: Optional[str] = None,
    ) -> UserResponse:
        """Register a new investigator account.

        Args:
            request: Registration payload.
            registered_by: Optional registering admin user ID.

        Returns:
            Public user response model.

        Raises:
            AuthenticationError: If password is weak or username/email exists.
            RoleNotFoundError: If the requested role cannot be resolved.
        """
        valid, failures = validate_password_strength(
            request.password,
            min_length=self._auth_settings.password_min_length,
        )
        if not valid:
            raise AuthenticationError(
                "Password does not meet strength requirements",
                context={"failures": failures},
            )
        if await self._user_repo.get_by_username(request.username) is not None:
            raise AuthenticationError(
                "Username already exists",
                context={"username": request.username},
            )
        if await self._user_repo.get_by_email(str(request.email)) is not None:
            raise AuthenticationError(
                "Email already exists",
                context={"email": str(request.email)},
            )
        role = await self._user_repo.get_role_by_name(request.role_name)
        if role is None:
            raise RoleNotFoundError(
                f"Role not found: {request.role_name}",
                context={"role_name": request.role_name},
            )
        if request.role_name.lower() == "admin":
            registrar_role = await self._registrar_role(registered_by)
            if registrar_role != "admin":
                raise InsufficientPermissionsError(
                    required_permission="users:create:admin",
                    user_role=registrar_role or "unknown",
                )
        user = UserORM(
            id=str(uuid4()),
            username=request.username,
            email=str(request.email),
            hashed_password=self._password_hasher.hash_password(request.password),
            full_name=request.full_name,
            role_id=role.id,
            is_active=True,
            is_locked=False,
            failed_login_attempts=0,
        )
        await self._user_repo.save(user)
        await self._audit(
            action="USER_REGISTERED",
            user_id=registered_by or user.id,
            details={"username": user.username, "role": role.name},
        )
        loaded = await self._user_repo.get(user.id)
        assert loaded is not None
        return self._to_response(loaded)

    async def authenticate(
        self,
        username: str,
        password: str,
        ip_address: str,
        user_agent: str,
    ) -> TokenResponse:
        """Authenticate a user and issue a token pair.

        Args:
            username: Account username.
            password: Plaintext password.
            ip_address: Client IP address.
            user_agent: Client user-agent string.

        Returns:
            Bearer token response.

        Raises:
            InvalidCredentialsError: If credentials are invalid.
            AccountLockedError: If the account is locked.
            AccountDisabledError: If the account is disabled.
        """
        user = await self._user_repo.get_by_username(username)
        if user is None:
            raise InvalidCredentialsError()
        if not user.is_active:
            raise AccountDisabledError(context={"username": username})
        if self._is_locked(user):
            raise AccountLockedError(locked_until=user.locked_until)

        if not self._password_hasher.verify_password(password, user.hashed_password):
            await self._user_repo.increment_failed_attempts(user.id)
            refreshed = await self._user_repo.get(user.id)
            attempts = refreshed.failed_login_attempts if refreshed else 0
            if attempts >= self._auth_settings.max_login_attempts:
                until = datetime.now(UTC) + timedelta(
                    minutes=self._auth_settings.lockout_duration_minutes
                )
                await self._user_repo.lock_user(user.id, until)
            raise InvalidCredentialsError()

        await self._user_repo.reset_failed_attempts(user.id)
        await self._user_repo.update_last_login(user.id)
        role_name = user.role.name if user.role is not None else "analyst"
        access, refresh, jti = self._jwt_handler.create_token_pair(
            user.id,
            user.username,
            role_name,
        )
        expires_at = datetime.now(UTC) + timedelta(
            minutes=self._jwt_handler.access_token_expire_minutes
        )
        # Persist refresh lifetime for session expiry tracking.
        expires_at = datetime.now(UTC) + timedelta(
            days=self._jwt_handler.refresh_token_expire_days
        )
        await self._session_repo.create_session(
            user.id,
            jti,
            expires_at,
            ip_address,
            user_agent,
        )
        await self._audit(
            action="USER_AUTHENTICATED",
            user_id=user.id,
            details={"username": user.username, "ip_address": ip_address},
        )
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            token_type="bearer",
            expires_in=self._jwt_handler.access_token_expire_minutes * 60,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Exchange a refresh token for a new token pair.

        Args:
            refresh_token: Existing refresh JWT.

        Returns:
            New bearer token response.
        """
        claims = self._jwt_handler.decode_token(refresh_token)
        if claims.get("type") != "refresh":
            raise TokenInvalidError("Refresh token required")
        jti = str(claims.get("jti", ""))
        user_id = str(claims.get("sub", ""))
        if not jti or not user_id:
            raise TokenInvalidError("Refresh token missing claims")
        if await self._session_repo.is_token_revoked(jti):
            raise TokenRevokedError(context={"jti": jti})
        await self._session_repo.revoke_session(jti)
        user = await self._user_repo.get(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User not found or inactive")
        role_name = user.role.name if user.role is not None else "analyst"
        access, refresh, new_jti = self._jwt_handler.create_token_pair(
            user.id,
            user.username,
            role_name,
        )
        expires_at = datetime.now(UTC) + timedelta(
            days=self._jwt_handler.refresh_token_expire_days
        )
        await self._session_repo.create_session(
            user.id,
            new_jti,
            expires_at,
            "refresh",
            "refresh",
        )
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            token_type="bearer",
            expires_in=self._jwt_handler.access_token_expire_minutes * 60,
        )

    async def logout(self, jti: str, user_id: str) -> None:
        """Revoke a single session for the user."""
        await self._session_repo.revoke_session(jti)
        await self._audit(
            action="USER_LOGGED_OUT",
            user_id=user_id,
            details={"jti": jti},
        )

    async def logout_all(self, user_id: str) -> int:
        """Revoke all sessions for a user.

        Returns:
            Number of sessions revoked.
        """
        count = await self._session_repo.revoke_all_user_sessions(user_id)
        await self._audit(
            action="USER_LOGGED_OUT_ALL",
            user_id=user_id,
            details={"revoked_count": count},
        )
        return count

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change a user's password after verifying the current one."""
        user = await self._user_repo.get(user_id)
        if user is None:
            raise AuthenticationError("User not found")
        if not self._password_hasher.verify_password(
            current_password,
            user.hashed_password,
        ):
            raise InvalidCredentialsError()
        valid, failures = validate_password_strength(
            new_password,
            min_length=self._auth_settings.password_min_length,
        )
        if not valid:
            raise AuthenticationError(
                "Password does not meet strength requirements",
                context={"failures": failures},
            )
        user.hashed_password = self._password_hasher.hash_password(new_password)
        await self._user_repo.save(user)
        await self._session_repo.revoke_all_user_sessions(user_id)
        await self._audit(action="PASSWORD_CHANGED", user_id=user_id, details={})

    async def get_user(self, user_id: str) -> UserResponse:
        """Return a public user profile."""
        user = await self._user_repo.get(user_id)
        if user is None:
            raise AuthenticationError("User not found", context={"user_id": user_id})
        return self._to_response(user)

    async def list_users(self) -> list[UserResponse]:
        """List all user profiles."""
        users = await self._user_repo.list_all()
        return [self._to_response(user) for user in users]

    async def deactivate_user(self, user_id: str, by_user_id: str) -> None:
        """Deactivate a user account."""
        user = await self._user_repo.get(user_id)
        if user is None:
            raise AuthenticationError("User not found", context={"user_id": user_id})
        user.is_active = False
        await self._user_repo.save(user)
        await self._session_repo.revoke_all_user_sessions(user_id)
        await self._audit(
            action="USER_DEACTIVATED",
            user_id=by_user_id,
            details={"target_user_id": user_id},
        )

    async def _audit(
        self,
        *,
        action: str,
        user_id: Optional[str],
        details: dict,
    ) -> None:
        """Append a database audit entry for a user action."""
        entry_number = await self._audit_repo.get_latest_entry_number() + 1
        entry = AuditEntry(
            entry_number=entry_number,
            stage=PipelineStage.EVALUATION,
            action=action,
            evidence_id="auth",
            details=details,
        )
        await self._audit_repo.log_entry(entry, user_id=user_id)

    async def _registrar_role(self, registered_by: Optional[str]) -> Optional[str]:
        """Return the registering user's role name, if known."""
        if not registered_by:
            return None
        registrar = await self._user_repo.get(registered_by)
        if registrar is None:
            return None
        role = getattr(registrar, "role", None)
        if role is not None and getattr(role, "name", None):
            return str(role.name)
        role_id = str(registrar.role_id)
        if role_id.startswith("role-"):
            return role_id.removeprefix("role-")
        return role_id

    @staticmethod
    def _is_locked(user: UserORM) -> bool:
        """Return whether the user account is currently locked."""
        if not user.is_locked:
            return False
        if user.locked_until is None:
            return True
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        return locked_until > datetime.now(UTC)

    @staticmethod
    def _to_response(user: UserORM) -> UserResponse:
        """Map a ``UserORM`` to ``UserResponse``."""
        role_name = user.role.name if user.role is not None else "unknown"
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role_name=role_name,
            is_active=user.is_active,
            last_login=user.last_login,
            created_at=user.created_at,
        )
