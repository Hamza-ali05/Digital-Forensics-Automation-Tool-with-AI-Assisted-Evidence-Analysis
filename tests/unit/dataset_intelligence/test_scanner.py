"""Unit tests for DatasetScanner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.dataset_intelligence.config import DatasetIntelligenceSettings
from dfat.dataset_intelligence.enums import DatasetFormat, DatasetStatus
from dfat.dataset_intelligence.scanner import DatasetScanner


@pytest.fixture
def scanner(tmp_path: Path) -> DatasetScanner:
    settings = DatasetIntelligenceSettings(
        datasets_dir=tmp_path / "datasets",
        max_dataset_size_gb=1.0,
    )
    settings.datasets_dir.mkdir(parents=True, exist_ok=True)
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    mime = MagicMock()
    mime.identify = MagicMock(return_value=("text/plain", "extension"))
    return DatasetScanner(settings, audit, mime)


@pytest.mark.asyncio
async def test_scan_missing_directory_returns_empty(
    scanner: DatasetScanner,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-datasets-dir"
    result = await scanner.scan(missing)
    assert result.discovered_count == 0
    assert result.datasets == []
    scanner._audit_service.log_action.assert_awaited()


@pytest.mark.asyncio
async def test_scan_discovers_csv_file(scanner: DatasetScanner, tmp_path: Path) -> None:
    sample = scanner._settings.datasets_dir / "benchmark" / "dfrws_sample.csv"
    sample.parent.mkdir(parents=True)
    sample.write_text("ioc_type,value\nhash,abc123\n", encoding="utf-8")

    result = await scanner.scan()

    assert result.discovered_count == 1
    record = result.datasets[0]
    assert record.format == DatasetFormat.CSV
    assert record.status == DatasetStatus.DISCOVERED
    assert record.hash_sha256


@pytest.mark.asyncio
async def test_scan_skips_hidden_files(scanner: DatasetScanner) -> None:
    base = scanner._settings.datasets_dir
    (base / ".hidden.csv").write_text("secret", encoding="utf-8")
    visible = base / "visible.csv"
    visible.write_text("ioc,value\n", encoding="utf-8")

    result = await scanner.scan()

    assert result.discovered_count == 1
    assert result.datasets[0].name == "visible.csv"


def test_detect_format_from_extension(scanner: DatasetScanner) -> None:
    assert scanner._detect_format(Path("capture.pcap")) == DatasetFormat.PCAP
    assert scanner._detect_format(Path("rules.yar")) == DatasetFormat.YARA_RULES
    scanner._mime_identifier.identify.return_value = ("application/octet-stream", "magic")
    assert scanner._detect_format(Path("unknown.bin")) == DatasetFormat.BINARY


@pytest.mark.asyncio
async def test_scan_single_returns_record(scanner: DatasetScanner) -> None:
    target = scanner._settings.datasets_dir / "single.json"
    target.write_text('{"iocs": []}', encoding="utf-8")

    record = await scanner.scan_single(target)

    assert record.name == "single.json"
    assert record.format == DatasetFormat.JSON
    assert record.file_size_bytes == target.stat().st_size
