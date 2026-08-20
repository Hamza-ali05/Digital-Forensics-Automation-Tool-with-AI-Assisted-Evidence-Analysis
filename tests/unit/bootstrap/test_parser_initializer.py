"""Unit tests for ParserInitializer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.bootstrap.parser_initializer import ParserInitializer
from dfat.core.enums import EvidenceType
from dfat.pipeline.parser_registry import ParserRegistry


def _register_parser(registry: ParserRegistry, name: str) -> None:
    parser = MagicMock()
    parser.parser_name = name
    parser.supported_evidence_types = MagicMock(
        return_value=[EvidenceType.DISK_IMAGE, EvidenceType.MEMORY_DUMP]
    )
    registry.register(parser)


@pytest.mark.asyncio
async def test_each_parser_checked_independently() -> None:
    registry = ParserRegistry()
    for name in ("FileSystemParser", "BrowserHistoryParser", "EventLogParser"):
        _register_parser(registry, name)

    with patch.object(
        ParserInitializer,
        "_check_library",
        side_effect=[
            (True, "20230901"),
            (True, "3.45.0"),
            (False, None),
        ],
    ) as check_mock:
        result = await ParserInitializer(registry).initialize()

    assert check_mock.call_count == 3
    assert result.phase == InitPhase.FORENSIC_PARSERS
    assert result.status == InitStatus.COMPLETED
    assert result.is_critical is False
    assert "EventLogParser" in result.degraded_capabilities
    assert result.details["parsers"]["EventLogParser"]["install"] == (
        "pip install python-evtx"
    )


@pytest.mark.asyncio
async def test_missing_library_includes_install_instructions(caplog: pytest.LogCaptureFixture) -> None:
    registry = ParserRegistry()
    _register_parser(registry, "FileSystemParser")

    with patch.object(ParserInitializer, "_check_library", return_value=(False, None)):
        result = await ParserInitializer(registry).initialize()

    assert result.degraded_capabilities == ["FileSystemParser"]
    assert "pip install pytsk3" in result.details["parsers"]["FileSystemParser"]["install"]
    assert any("pip install pytsk3" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_all_parsers_unavailable_returns_degraded() -> None:
    registry = ParserRegistry()
    _register_parser(registry, "FileSystemParser")
    _register_parser(registry, "RegistryParser")

    with patch.object(ParserInitializer, "_check_library", return_value=(False, None)):
        result = await ParserInitializer(registry).initialize()

    assert result.status == InitStatus.DEGRADED
    assert set(result.degraded_capabilities) == {"FileSystemParser", "RegistryParser"}


@pytest.mark.asyncio
async def test_check_library_detects_sqlite3_builtin() -> None:
    available, version_str = ParserInitializer(ParserRegistry())._check_library("sqlite3")
    assert available is True
    assert version_str is not None
