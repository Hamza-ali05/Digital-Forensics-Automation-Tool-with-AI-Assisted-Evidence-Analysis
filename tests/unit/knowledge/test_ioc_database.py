"""Unit tests for IOCKnowledgeBase."""

from __future__ import annotations

from pathlib import Path

import pytest

from dfat.dataset_intelligence.enums import DatasetCategory, DatasetFormat, DatasetStatus
from dfat.dataset_intelligence.models import DatasetRecord
from dfat.knowledge.ioc_database import IOCEntry, IOCKnowledgeBase


def _dataset(path: Path) -> DatasetRecord:
    return DatasetRecord(
        name=path.name,
        file_path=path,
        category=DatasetCategory.THREAT_INTELLIGENCE,
        format=DatasetFormat.CSV,
        status=DatasetStatus.READY,
        file_size_bytes=path.stat().st_size,
        hash_sha256="b" * 64,
        parent_directory=str(path.parent),
    )


@pytest.mark.asyncio
async def test_add_entries_and_lookup(tmp_path: Path) -> None:
    kb = IOCKnowledgeBase(tmp_path / "ioc.db")
    await kb.add_entries(
        [
            IOCEntry(
                ioc_id="ioc-1",
                ioc_type="hash",
                value="deadbeef",
                source_dataset="test",
                confidence="high",
            )
        ]
    )
    match = await kb.lookup_hash("deadbeef")
    assert len(match) == 1
    assert match[0].ioc_id


@pytest.mark.asyncio
async def test_ingest_csv_dataset(tmp_path: Path) -> None:
    csv_path = tmp_path / "iocs.csv"
    csv_path.write_text("ioc_type,value\nhash,abc123\nip,203.0.113.1\n", encoding="utf-8")
    kb = IOCKnowledgeBase(tmp_path / "ioc2.db")
    count = await kb.ingest_from_dataset(_dataset(csv_path))
    assert count == 2
    stats = await kb.get_statistics()
    assert stats["total_count"] >= 2


@pytest.mark.asyncio
async def test_search_substring(tmp_path: Path) -> None:
    kb = IOCKnowledgeBase(tmp_path / "ioc3.db")
    await kb.add_entries(
        [
            IOCEntry(
                ioc_id="ioc-a",
                ioc_type="domain",
                value="evil.example.com",
                source_dataset="test",
                confidence="medium",
            )
        ]
    )
    matches = await kb.search("evil.example")
    assert len(matches) == 1
    assert matches[0].value == "evil.example.com"


@pytest.mark.asyncio
async def test_export_all_returns_entries(tmp_path: Path) -> None:
    kb = IOCKnowledgeBase(tmp_path / "ioc4.db")
    await kb.add_entries(
        [
            IOCEntry(
                ioc_id="ioc-x",
                ioc_type="process",
                value="mimikatz.exe",
                source_dataset="test",
                confidence="high",
            )
        ]
    )
    exported = await kb.export_all()
    assert len(exported) == 1
    assert exported[0].value == "mimikatz.exe"
