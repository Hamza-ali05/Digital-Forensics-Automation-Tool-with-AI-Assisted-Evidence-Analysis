"""Unit tests for DirectoryManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from dfat.bootstrap.directory_manager import DirectoryManager
from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.settings import load_settings


@pytest.mark.asyncio
async def test_creates_missing_directories(tmp_path: Path) -> None:
    settings = load_settings(env="development")
    settings.logging.audit_log_path = tmp_path / "audit.log"
    manager = DirectoryManager(base_dir=tmp_path)

    result = await manager.validate_and_create(settings)

    assert result.phase == InitPhase.DIRECTORIES
    assert result.status == InitStatus.COMPLETED
    assert result.is_critical is True
    assert len(result.details["created"]) == len(DirectoryManager.REQUIRED_DIRECTORIES)
    for relative, _ in DirectoryManager.REQUIRED_DIRECTORIES:
        assert (tmp_path / relative).is_dir()


@pytest.mark.asyncio
async def test_existing_directories_are_not_recreated(tmp_path: Path) -> None:
    settings = load_settings(env="development")
    settings.logging.audit_log_path = tmp_path / "audit.log"
    manager = DirectoryManager(base_dir=tmp_path)

    first = await manager.validate_and_create(settings)
    marker = tmp_path / "data" / "evidence" / "keep-me.txt"
    marker.write_text("preserved", encoding="utf-8")
    mtime_before = marker.stat().st_mtime

    second = await manager.validate_and_create(settings)

    assert first.status == InitStatus.COMPLETED
    assert second.status == InitStatus.COMPLETED
    assert second.details["created"] == []
    assert marker.read_text(encoding="utf-8") == "preserved"
    assert marker.stat().st_mtime == mtime_before


@pytest.mark.asyncio
async def test_file_conflict_fails_directory_validation(tmp_path: Path) -> None:
    """A required path that is a file (not a directory) is a critical failure."""
    settings = load_settings(env="development")
    settings.logging.audit_log_path = tmp_path / "audit.log"
    conflict = tmp_path / "data" / "evidence"
    conflict.parent.mkdir(parents=True, exist_ok=True)
    conflict.write_text("not-a-directory", encoding="utf-8")

    result = await DirectoryManager(base_dir=tmp_path).validate_and_create(settings)

    assert result.phase == InitPhase.DIRECTORIES
    assert result.status == InitStatus.FAILED
    assert result.is_critical is True
    assert result.error is not None
    assert "not a directory" in result.error.lower()
