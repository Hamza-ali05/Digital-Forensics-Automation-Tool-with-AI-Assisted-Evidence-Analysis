"""Database connectivity, schema, migrations, and role seed bootstrap."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.database.base import Base
from dfat.database.engine import DatabaseEngine
from dfat.database.models.user import RoleORM
from dfat.settings import DatabaseSettings

logger = logging.getLogger(__name__)

_ALEMBIC_INI = (
    Path(__file__).resolve().parents[1] / "database" / "migrations" / "alembic.ini"
)
_EXPECTED_ROLE_NAMES = ("admin", "investigator", "analyst", "viewer")
_ROLE_SEEDS: list[dict[str, Any]] = [
    {
        "id": "role-admin",
        "name": "admin",
        "description": "Full system administrator",
        "permissions": '{"all": true}',
        "is_active": True,
    },
    {
        "id": "role-investigator",
        "name": "investigator",
        "description": "Lead forensic investigator with full analysis access",
        "permissions": (
            '{"evidence": ["create","read","update","delete"],'
            '"analysis": ["create","read"],'
            '"reports": ["create","read"],'
            '"evaluation": ["create","read"]}'
        ),
        "is_active": True,
    },
    {
        "id": "role-analyst",
        "name": "analyst",
        "description": "Forensic analyst with read and analysis access",
        "permissions": (
            '{"evidence": ["read"],'
            '"analysis": ["create","read"],'
            '"reports": ["read"],'
            '"evaluation": ["read"]}'
        ),
        "is_active": True,
    },
    {
        "id": "role-viewer",
        "name": "viewer",
        "description": "Read-only access to reports",
        "permissions": '{"reports": ["read"],"evaluation": ["read"]}',
        "is_active": True,
    },
]


class DatabaseInitializer:
    """Verify database connectivity, apply migrations, and ensure role seeds."""

    def __init__(
        self,
        db_engine: DatabaseEngine,
        settings: DatabaseSettings,
    ) -> None:
        """Initialise the database bootstrap helper.

        Args:
            db_engine: Async SQLAlchemy engine wrapper.
            settings: Database settings (URL, create_tables flag, etc.).
        """
        self._db_engine = db_engine
        self._settings = settings

    async def initialize(self) -> PhaseResult:
        """Run connectivity, schema, migration, and seed checks.

        Returns:
            ``PhaseResult`` with ``COMPLETED`` or ``FAILED``.
        """
        started = time.perf_counter()
        details: dict[str, Any] = {}

        # Ensure ORM models are registered on Base.metadata.
        import dfat.database  # noqa: F401

        try:
            connected = await self._db_engine.check_connection()
        except Exception as exc:  # noqa: BLE001
            return self._failed(
                started,
                f"Database connectivity check raised: {exc}. "
                "Verify DFAT_DATABASE__URL and that the database service is running.",
                details,
            )

        if not connected:
            return self._failed(
                started,
                "Database connection failed (SELECT 1). "
                f"Check DFAT_DATABASE__URL={self._settings.url!r} and network/credentials.",
                details,
            )
        details["connectivity"] = True

        try:
            if self._settings.create_tables_on_startup:
                await self._db_engine.create_tables()
                details["create_tables_on_startup"] = True

            pending_before = await self._get_pending_migrations()
            details["pending_migrations_before"] = pending_before

            revision = await self._apply_migrations()
            details["migration_revision"] = revision
            logger.info("Database migration revision: %s", revision)
            if revision is None:
                return self._failed(
                    started,
                    "Alembic revision is unknown after migration/stamp. "
                    "Verify alembic_version table and DFAT_DATABASE__URL.",
                    details,
                )

            missing_tables = await self._missing_tables()
            details["expected_tables"] = sorted(Base.metadata.tables.keys())
            details["missing_tables"] = missing_tables
            if missing_tables:
                return self._failed(
                    started,
                    "Expected tables missing after migrations: "
                    f"{', '.join(missing_tables)}. "
                    "Run `alembic upgrade head` manually or inspect migration history.",
                    details,
                )

            seeds_ok = await self._verify_seed_data()
            details["seed_roles_ok"] = seeds_ok
            if not seeds_ok:
                return self._failed(
                    started,
                    "Default RBAC roles are incomplete after seed verification. "
                    "Expected roles: admin, investigator, analyst, viewer.",
                    details,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Database initialization failed")
            return self._failed(
                started,
                f"Database initialization error: {exc}. "
                "Inspect alembic history and database logs.",
                details,
            )

        duration_ms = (time.perf_counter() - started) * 1000.0
        return PhaseResult(
            phase=InitPhase.DATABASE,
            status=InitStatus.COMPLETED,
            duration_ms=duration_ms,
            message=(
                f"Database ready (revision={details.get('migration_revision')}, "
                "seed roles verified)"
            ),
            details=details,
            is_critical=True,
        )

    async def _get_current_revision(self) -> Optional[str]:
        """Return the current Alembic revision, if any."""

        def _read(sync_conn: Any) -> Optional[str]:
            context = MigrationContext.configure(sync_conn)
            return context.get_current_revision()

        async with self._db_engine.engine.connect() as connection:
            return await connection.run_sync(_read)

    async def _get_pending_migrations(self) -> list[str]:
        """Return revision IDs pending relative to the current database."""
        cfg = self._alembic_config()
        script = ScriptDirectory.from_config(cfg)
        current = await self._get_current_revision()

        def _pending(sync_conn: Any) -> list[str]:
            context = MigrationContext.configure(sync_conn)
            current_rev = context.get_current_revision()
            if current_rev is None:
                return [rev.revision for rev in script.walk_revisions()]
            pending: list[str] = []
            for rev in script.iterate_revisions("heads", current_rev):
                if rev.revision != current_rev:
                    pending.append(rev.revision)
            return list(reversed(pending))

        async with self._db_engine.engine.connect() as connection:
            result = await connection.run_sync(_pending)
        # Prefer async-read current for logging consistency.
        details_current = current
        logger.debug(
            "Alembic current=%s pending=%s",
            details_current,
            result,
        )
        return result

    async def _verify_seed_data(self) -> bool:
        """Ensure the four default roles exist; insert any that are missing."""
        async with self._db_engine.session_factory() as session:
            result = await session.execute(select(RoleORM.name))
            existing = {row[0] for row in result.all()}
            missing = [name for name in _EXPECTED_ROLE_NAMES if name not in existing]
            if not missing:
                await session.commit()
                return True

            seeds_by_name = {str(seed["name"]): seed for seed in _ROLE_SEEDS}
            for name in missing:
                seed = seeds_by_name[name]
                session.add(
                    RoleORM(
                        id=str(seed["id"]),
                        name=str(seed["name"]),
                        description=str(seed["description"]),
                        permissions=str(seed["permissions"]),
                        is_active=bool(seed["is_active"]),
                    )
                )
                logger.info("Inserted missing seed role: %s", name)
            await session.commit()

            result = await session.execute(select(RoleORM.name))
            existing = {row[0] for row in result.all()}
            return all(name in existing for name in _EXPECTED_ROLE_NAMES)

    async def _apply_migrations(self) -> Optional[str]:
        """Apply Alembic upgrades (or stamp head when schema already exists)."""
        current = await self._get_current_revision()
        table_names = await self._list_table_names()
        expected = set(Base.metadata.tables.keys())
        has_schema = bool(expected.intersection(table_names))

        if current is None and has_schema:
            # create_tables_on_startup (or prior create_all) built schema without
            # alembic_version — stamp head instead of re-running create migrations.
            await asyncio.to_thread(self._stamp_head)
            return await self._get_current_revision()

        pending = await self._get_pending_migrations()
        if current is None or pending:
            await asyncio.to_thread(self._upgrade_head)
        return await self._get_current_revision()

    async def _list_table_names(self) -> set[str]:
        """Return table names present in the connected database."""

        def _names(sync_conn: Any) -> set[str]:
            return set(inspect(sync_conn).get_table_names())

        async with self._db_engine.engine.connect() as connection:
            return await connection.run_sync(_names)

    async def _missing_tables(self) -> list[str]:
        """Return expected ORM table names that are absent from the database."""
        present = await self._list_table_names()
        expected = set(Base.metadata.tables.keys())
        return sorted(expected - present)

    def _alembic_config(self) -> Config:
        """Build an Alembic config bound to this initializer's database URL."""
        cfg = Config(str(_ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", self._settings.url)
        cfg.set_main_option(
            "script_location",
            str(_ALEMBIC_INI.parent),
        )
        return cfg

    def _upgrade_head(self) -> None:
        """Run ``alembic upgrade head`` against this initializer's database URL."""
        self._run_alembic(lambda cfg: command.upgrade(cfg, "head"))

    def _stamp_head(self) -> None:
        """Stamp the database as being at Alembic head without running upgrades."""
        self._run_alembic(lambda cfg: command.stamp(cfg, "head"))

    def _run_alembic(self, action: Any) -> None:
        """Execute an Alembic command with settings forced to this database URL.

        ``env.py`` resolves the URL via ``load_settings()``, which prefers YAML
        init values over ``DFAT_DATABASE__URL``. Temporarily patching
        ``load_settings`` ensures migrations target the initializer engine.
        """
        import dfat.settings as settings_module

        target_url = self._settings.url
        original = settings_module.load_settings

        def _load_for_migration(*args: Any, **kwargs: Any) -> Any:
            loaded = original(*args, **kwargs)
            return loaded.model_copy(
                update={
                    "database": loaded.database.model_copy(update={"url": target_url}),
                }
            )

        settings_module.load_settings = _load_for_migration  # type: ignore[assignment]
        previous = os.environ.get("DFAT_DATABASE__URL")
        os.environ["DFAT_DATABASE__URL"] = target_url
        try:
            action(self._alembic_config())
        finally:
            settings_module.load_settings = original  # type: ignore[assignment]
            if previous is None:
                os.environ.pop("DFAT_DATABASE__URL", None)
            else:
                os.environ["DFAT_DATABASE__URL"] = previous

    def _failed(
        self,
        started: float,
        error: str,
        details: dict[str, Any],
    ) -> PhaseResult:
        """Build a FAILED phase result."""
        duration_ms = (time.perf_counter() - started) * 1000.0
        logger.error("Database initialization failed: %s", error)
        return PhaseResult(
            phase=InitPhase.DATABASE,
            status=InitStatus.FAILED,
            duration_ms=duration_ms,
            message="Database initialization failed — startup aborted",
            details=details,
            error=error,
            is_critical=True,
        )
