"""Unit tests for SQLAlchemy QueryMonitor slow-query logging."""

from __future__ import annotations

import logging

import pytest

from dfat.database.engine import DatabaseEngine
from dfat.database.query_monitor import QueryMonitor


@pytest.mark.asyncio
async def test_query_monitor_logs_queries_over_threshold(
    db_engine: DatabaseEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Queries slower than the threshold are logged with SQL and duration."""
    monitor = QueryMonitor(threshold_ms=0)
    monitor.attach(db_engine.engine)
    try:
        with caplog.at_level(logging.WARNING, logger="dfat.database.query_monitor"):
            ok = await db_engine.check_connection()
        assert ok is True
        assert any("Slow query" in record.getMessage() for record in caplog.records)
        assert any("SELECT" in record.getMessage().upper() for record in caplog.records)
    finally:
        monitor.detach(db_engine.engine)


@pytest.mark.asyncio
async def test_engine_attaches_query_monitor_when_enabled(tmp_path) -> None:
    """DatabaseEngine wires QueryMonitor when enable_query_monitoring is True."""
    db_path = tmp_path / "monitor.db"
    engine = DatabaseEngine(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        echo=False,
        enable_query_monitoring=True,
        slow_query_threshold_ms=0,
    )
    try:
        assert engine._query_monitor is not None
        ok = await engine.check_connection()
        assert ok is True
    finally:
        await engine.dispose()
    assert engine._query_monitor is None
