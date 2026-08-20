"""Authentication system bootstrap and session housekeeping."""

from __future__ import annotations

import logging
import os
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import delete, select

from dfat.auth.jwt_handler import JWTHandler
from dfat.auth.password import PasswordHasher, validate_password_strength
from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.database.models.session_orm import SessionORM
from dfat.database.models.user import RoleORM, UserORM
from dfat.database.repositories.session_repo import SessionRepository
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)

_DEFAULT_ADMIN_USERNAME = "admin"
_DEFAULT_ADMIN_EMAIL = "admin@dfat.local"
_DEFAULT_ADMIN_FULL_NAME = "DFAT Administrator"
_EXPECTED_ROLE_NAMES = ("admin", "investigator", "analyst", "viewer")
_SESSION_RETENTION_DAYS = 7


class AuthInitializer:
    """Verify authentication readiness and ensure a default admin account exists."""

    def __init__(
        self,
        user_repo: SQLAlchemyUserRepository,
        password_hasher: PasswordHasher,
        jwt_handler: JWTHandler,
        settings: DFATSettings,
    ) -> None:
        """Initialise the auth bootstrap helper.

        Args:
            user_repo: User and role persistence repository.
            password_hasher: Password hashing service.
            jwt_handler: JWT creation and validation service.
            settings: Application settings (auth policy, environment).
        """
        self._user_repo = user_repo
        self._password_hasher = password_hasher
        self._jwt_handler = jwt_handler
        self._settings = settings
        self._session_repo = SessionRepository(user_repo._session_factory)

    async def initialize(self) -> PhaseResult:
        """Run JWT, password, admin, role, and session cleanup checks.

        Returns:
            ``PhaseResult`` with ``COMPLETED`` or ``FAILED``.
        """
        started = time.perf_counter()
        details: dict[str, Any] = {}

        try:
            jwt_ok = self._verify_jwt_round_trip()
            details["jwt_round_trip"] = jwt_ok
            if not jwt_ok:
                return self._failed(
                    started,
                    "JWT handler failed create/decode round-trip. "
                    "Check DFAT_AUTH__SECRET_KEY and algorithm settings.",
                    details,
                )

            password_ok = self._verify_password_hasher()
            details["password_hasher"] = password_ok
            if not password_ok:
                return self._failed(
                    started,
                    "Password hasher failed hash/verify round-trip.",
                    details,
                )

            admin_created, admin_password_generated = await self._ensure_admin_exists()
            details["admin_created"] = admin_created
            details["admin_password_generated"] = admin_password_generated

            roles_ok, role_coverage = await self._verify_role_coverage()
            details["role_coverage"] = role_coverage
            if not roles_ok:
                missing = [
                    name
                    for name, count in role_coverage.items()
                    if count < 1
                ]
                return self._failed(
                    started,
                    "At least one active user is required for each role. "
                    f"Missing users for: {', '.join(missing)}.",
                    details,
                )

            cleaned = await self._cleanup_expired_sessions()
            details["expired_sessions_removed"] = cleaned
        except Exception as exc:  # noqa: BLE001
            logger.exception("Auth initialization failed")
            return self._failed(
                started,
                f"Authentication initialization error: {exc}",
                details,
            )

        duration_ms = (time.perf_counter() - started) * 1000.0
        return PhaseResult(
            phase=InitPhase.AUTHENTICATION,
            status=InitStatus.COMPLETED,
            duration_ms=duration_ms,
            message="Authentication system ready",
            details=details,
            is_critical=True,
        )

    async def _ensure_admin_exists(self) -> tuple[bool, bool]:
        """Create the default admin account when none exists.

        Returns:
            Tuple of ``(admin_present, password_was_generated)``.
        """
        existing = await self._user_repo.get_by_username(_DEFAULT_ADMIN_USERNAME)
        if existing is not None:
            return True, False

        role = await self._user_repo.get_role_by_name("admin")
        if role is None:
            raise RuntimeError(
                "Admin role is missing from the database. "
                "Run database initialization before auth bootstrap."
            )

        password = os.environ.get("DFAT_ADMIN_PASSWORD", "").strip()
        generated = False
        if not password:
            password = self._generate_admin_password()
            generated = True
            print(  # noqa: T201 — intentional first-run operator notice
                "\n=== DFAT first-run admin credentials ===\n"
                f"  username: {_DEFAULT_ADMIN_USERNAME}\n"
                f"  password: {password}\n"
                "  Set DFAT_ADMIN_PASSWORD to suppress auto-generation.\n"
                "========================================\n",
                flush=True,
            )
            logger.warning(
                "Generated default admin password for first run (see console output)"
            )

        valid, failures = validate_password_strength(
            password,
            min_length=self._settings.auth.password_min_length,
        )
        if not valid:
            raise ValueError(
                "Admin password does not meet strength requirements: "
                + "; ".join(failures)
            )

        admin = UserORM(
            id=str(uuid4()),
            username=_DEFAULT_ADMIN_USERNAME,
            email=_DEFAULT_ADMIN_EMAIL,
            hashed_password=self._password_hasher.hash_password(password),
            full_name=_DEFAULT_ADMIN_FULL_NAME,
            role_id=role.id,
            is_active=True,
            is_locked=False,
            failed_login_attempts=0,
        )
        await self._user_repo.save(admin)
        logger.info("Created default admin user %s", _DEFAULT_ADMIN_USERNAME)
        return True, generated

    async def _cleanup_expired_sessions(self) -> int:
        """Remove sessions older than seven days.

        Returns:
            Number of deleted session rows.
        """
        cutoff = datetime.now(UTC) - timedelta(days=_SESSION_RETENTION_DAYS)
        async with self._user_repo._session_factory() as session:
            result = await session.execute(
                delete(SessionORM).where(SessionORM.expires_at < cutoff)
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def _verify_role_coverage(self) -> tuple[bool, dict[str, int]]:
        """Verify role definitions exist and each role has at least one active user."""
        coverage: dict[str, int] = {name: 0 for name in _EXPECTED_ROLE_NAMES}
        users = await self._user_repo.list_all()
        for user in users:
            if not user.is_active:
                continue
            role = getattr(user, "role", None)
            role_name = getattr(role, "name", None) if role is not None else None
            if role_name in coverage:
                coverage[str(role_name)] += 1

        for name in _EXPECTED_ROLE_NAMES:
            role = await self._user_repo.get_role_by_name(name)
            if role is None:
                raise RuntimeError(f"Role definition missing: {name}")

        return all(count >= 1 for count in coverage.values()), coverage

    def _verify_jwt_round_trip(self) -> bool:
        """Return whether JWT create/decode round-trip succeeds."""
        token = self._jwt_handler.create_access_token(
            user_id="bootstrap-test",
            username="bootstrap",
            role="admin",
        )
        claims = self._jwt_handler.decode_token(token)
        return (
            claims.get("sub") == "bootstrap-test"
            and claims.get("username") == "bootstrap"
            and claims.get("role") == "admin"
            and claims.get("type") == "access"
        )

    def _verify_password_hasher(self) -> bool:
        """Return whether password hash/verify round-trip succeeds."""
        probe = "Df@t-Bootstrap-Probe-2026!"
        hashed = self._password_hasher.hash_password(probe)
        return self._password_hasher.verify_password(probe, hashed)

    @staticmethod
    def _generate_admin_password() -> str:
        """Generate a strong random admin password for first-run bootstrap."""
        core = secrets.token_urlsafe(12)
        return f"Df@t-{core}1A!"

    def _failed(
        self,
        started: float,
        error: str,
        details: dict[str, Any],
    ) -> PhaseResult:
        """Build a FAILED authentication phase result."""
        duration_ms = (time.perf_counter() - started) * 1000.0
        logger.error("Auth initialization failed: %s", error)
        return PhaseResult(
            phase=InitPhase.AUTHENTICATION,
            status=InitStatus.FAILED,
            duration_ms=duration_ms,
            message="Authentication initialization failed — startup aborted",
            details=details,
            error=error,
            is_critical=True,
        )
