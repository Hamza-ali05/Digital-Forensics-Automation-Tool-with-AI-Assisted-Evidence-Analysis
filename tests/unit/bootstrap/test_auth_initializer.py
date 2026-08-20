"""Unit tests for AuthInitializer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from dfat.auth.jwt_handler import JWTHandler
from dfat.auth.password import PasswordHasher
from dfat.bootstrap.auth_initializer import AuthInitializer
from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.database.engine import DatabaseEngine
from dfat.database.models.session_orm import SessionORM
from dfat.database.models.user import RoleORM, UserORM
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository
from dfat.settings import DFATSettings, load_settings


async def _seed_roles(engine: DatabaseEngine) -> None:
    roles = [
        ("role-admin", "admin"),
        ("role-investigator", "investigator"),
        ("role-analyst", "analyst"),
        ("role-viewer", "viewer"),
    ]
    async with engine.session_factory() as session:
        for role_id, name in roles:
            session.add(
                RoleORM(
                    id=role_id,
                    name=name,
                    description=f"{name} role",
                    permissions="{}",
                    is_active=True,
                )
            )
        await session.commit()


async def _seed_user_for_role(
    engine: DatabaseEngine,
    *,
    username: str,
    role_id: str,
    email: str,
    hasher: PasswordHasher,
) -> None:
    async with engine.session_factory() as session:
        session.add(
            UserORM(
                id=str(uuid4()),
                username=username,
                email=email,
                hashed_password=hasher.hash_password("ProbePass123!"),
                full_name=username.title(),
                role_id=role_id,
                is_active=True,
                is_locked=False,
                failed_login_attempts=0,
            )
        )
        await session.commit()


def _auth_initializer(
    engine: DatabaseEngine,
    settings: DFATSettings | None = None,
) -> AuthInitializer:
    settings = settings or load_settings(env="development")
    hasher = PasswordHasher()
    jwt_handler = JWTHandler(
        secret_key=settings.auth.secret_key,
        algorithm=settings.auth.algorithm,
        access_token_expire_minutes=settings.auth.access_token_expire_minutes,
        refresh_token_expire_days=settings.auth.refresh_token_expire_days,
    )
    return AuthInitializer(
        user_repo=SQLAlchemyUserRepository(engine.session_factory),
        password_hasher=hasher,
        jwt_handler=jwt_handler,
        settings=settings,
    )


@pytest.mark.asyncio
async def test_ensure_admin_created_on_first_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "auth.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = DatabaseEngine(database_url=url, echo=False)
    monkeypatch.setenv("DFAT_ADMIN_PASSWORD", "AdminBootstrap123!")
    try:
        await engine.create_tables()
        await _seed_roles(engine)
        initializer = _auth_initializer(engine)
        created, generated = await initializer._ensure_admin_exists()
        assert created is True
        assert generated is False

        admin = await initializer._user_repo.get_by_username("admin")
        assert admin is not None
        assert admin.role.name == "admin"
        assert initializer._password_hasher.verify_password(
            "AdminBootstrap123!",
            admin.hashed_password,
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_jwt_round_trip_and_password_hasher() -> None:
    settings = load_settings(env="development")
    initializer = AuthInitializer(
        user_repo=SQLAlchemyUserRepository(
            DatabaseEngine("sqlite+aiosqlite:///:memory:").session_factory
        ),
        password_hasher=PasswordHasher(),
        jwt_handler=JWTHandler(
            secret_key=settings.auth.secret_key,
            algorithm=settings.auth.algorithm,
            access_token_expire_minutes=settings.auth.access_token_expire_minutes,
        ),
        settings=settings,
    )
    assert initializer._verify_jwt_round_trip() is True
    assert initializer._verify_password_hasher() is True


@pytest.mark.asyncio
async def test_initialize_completes_when_each_role_has_user(tmp_path: Path) -> None:
    db_path = tmp_path / "auth-full.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = DatabaseEngine(database_url=url, echo=False)
    hasher = PasswordHasher()
    try:
        await engine.create_tables()
        await _seed_roles(engine)
        await _seed_user_for_role(
            engine,
            username="admin",
            role_id="role-admin",
            email="admin@test.local",
            hasher=hasher,
        )
        await _seed_user_for_role(
            engine,
            username="investigator1",
            role_id="role-investigator",
            email="inv@test.local",
            hasher=hasher,
        )
        await _seed_user_for_role(
            engine,
            username="analyst1",
            role_id="role-analyst",
            email="analyst@test.local",
            hasher=hasher,
        )
        await _seed_user_for_role(
            engine,
            username="viewer1",
            role_id="role-viewer",
            email="viewer@test.local",
            hasher=hasher,
        )

        result = await _auth_initializer(engine).initialize()
        assert result.phase == InitPhase.AUTHENTICATION
        assert result.status == InitStatus.COMPLETED
        assert result.details["jwt_round_trip"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_expired_sessions(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = DatabaseEngine(database_url=url, echo=False)
    try:
        await engine.create_tables()
        old_expiry = datetime.now(UTC) - timedelta(days=10)
        async with engine.session_factory() as session:
            session.add(
                SessionORM(
                    id=str(uuid4()),
                    user_id=str(uuid4()),
                    token_jti=str(uuid4()),
                    ip_address="127.0.0.1",
                    user_agent="test",
                    expires_at=old_expiry,
                    is_revoked=False,
                )
            )
            await session.commit()

        initializer = _auth_initializer(engine)
        removed = await initializer._cleanup_expired_sessions()
        assert removed == 1

        async with engine.session_factory() as session:
            count = len((await session.execute(select(SessionORM))).scalars().all())
        assert count == 0
    finally:
        await engine.dispose()
