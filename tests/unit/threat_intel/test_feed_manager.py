"""Unit tests for ThreatFeedManager."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.dataset_intelligence.enums import DatasetCategory, DatasetFormat, DatasetStatus
from dfat.dataset_intelligence.models import DatasetRecord
from dfat.knowledge.ioc_database import IOCEntry
from dfat.threat_intel.feed_manager import ThreatFeedManager
from dfat.threat_intel.mitre_mapper import MITREMapper
from dfat.threat_intel.sigma_engine import SigmaEngine
from dfat.threat_intel.stix_handler import STIXHandler
from dfat.threat_intel.yara_engine import YARAEngine


def _dataset(
    tmp_path: Path,
    *,
    name: str,
    fmt: DatasetFormat,
    content: str,
    suffix: str,
) -> DatasetRecord:
    file_path = tmp_path / f"{name}{suffix}"
    file_path.write_text(content, encoding="utf-8")
    return DatasetRecord(
        dataset_id=f"ds-{name}",
        name=name,
        file_path=file_path,
        category=DatasetCategory.THREAT_INTELLIGENCE,
        format=fmt,
        status=DatasetStatus.READY,
        file_size_bytes=file_path.stat().st_size,
        hash_sha256="abc123",
        parent_directory=str(tmp_path),
    )


def _manager(
    tmp_path: Path,
    *,
    ioc_kb: MagicMock | None = None,
) -> ThreatFeedManager:
    yara_dir = tmp_path / "yara"
    sigma_dir = tmp_path / "sigma"
    yara_dir.mkdir(parents=True, exist_ok=True)
    sigma_dir.mkdir(parents=True, exist_ok=True)

    kb = ioc_kb or MagicMock(
        add_entries=AsyncMock(return_value=1),
        get_statistics=AsyncMock(return_value={"total_count": 5, "by_type": {"domain": 5}}),
        _parse_dataset=MagicMock(return_value=[]),
    )
    graph = MagicMock(add_ioc_relationships=MagicMock(return_value=1), save=MagicMock())
    audit = MagicMock(log_action=AsyncMock())

    return ThreatFeedManager(
        dataset_registry=MagicMock(),
        ioc_kb=kb,
        yara_engine=YARAEngine(yara_dir),
        sigma_engine=SigmaEngine(sigma_dir),
        mitre_mapper=MITREMapper(),
        knowledge_graph=graph,
        audit_service=audit,
        stix_handler=STIXHandler(),
    )


@pytest.mark.asyncio
async def test_ingest_sigma_rules_stages_and_loads(tmp_path: Path) -> None:
    dataset = _dataset(
        tmp_path,
        name="sigma-feed",
        fmt=DatasetFormat.SIGMA_RULES,
        suffix=".yml",
        content=(
            "title: Test Sigma\n"
            "id: test-001\n"
            "logsource:\n  product: windows\n  category: process_creation\n"
            "detection:\n  selection:\n    CommandLine|contains: mimikatz\n"
            "  condition: selection\n"
        ),
    )
    manager = _manager(tmp_path)
    result = await manager.ingest_feed(dataset)

    assert result.feed_type == DatasetFormat.SIGMA_RULES.value
    assert result.rules_loaded == 1
    assert result.items_ingested == 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_ingest_stix_bundle_adds_iocs(tmp_path: Path) -> None:
    bundle = {
        "type": "bundle",
        "id": "bundle--1",
        "objects": [
            {
                "type": "indicator",
                "id": "indicator--1",
                "name": "evil",
                "labels": ["high"],
                "pattern": "[domain-name:value = 'evil.example.com']",
            }
        ],
    }
    dataset = _dataset(
        tmp_path,
        name="stix-feed",
        fmt=DatasetFormat.STIX_BUNDLE,
        suffix=".json",
        content=json.dumps(bundle),
    )
    ioc_kb = MagicMock(
        add_entries=AsyncMock(return_value=1),
        get_statistics=AsyncMock(return_value={"total_count": 1, "by_type": {}}),
    )
    manager = _manager(tmp_path, ioc_kb=ioc_kb)
    result = await manager.ingest_feed(dataset)

    assert result.items_ingested == 1
    ioc_kb.add_entries.assert_awaited_once()


@pytest.mark.asyncio
async def test_scan_artefacts_against_intel_returns_findings(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    sigma_dir = tmp_path / "sigma"
    (sigma_dir / "proc.yml").write_text(
        (
            "title: Mimikatz Process\n"
            "id: sigma-001\n"
            "logsource:\n  product: windows\n  category: process_creation\n"
            "detection:\n  selection:\n    CommandLine|contains: mimikatz\n"
            "  condition: selection\n"
        ),
        encoding="utf-8",
    )
    manager._sigma.load_rules()

    ioc_kb = MagicMock(
        lookup_process_name=AsyncMock(
            return_value=[
                IOCEntry(
                    ioc_type="process",
                    value="mimikatz.exe",
                    source_dataset="feed",
                    confidence="high",
                )
            ]
        ),
        lookup_hash=AsyncMock(return_value=[]),
        lookup_ip=AsyncMock(return_value=[]),
        lookup_domain=AsyncMock(return_value=[]),
        lookup_registry_key=AsyncMock(return_value=[]),
        search=AsyncMock(return_value=[]),
        get_statistics=AsyncMock(return_value={"total_count": 0, "by_type": {}}),
    )
    manager._ioc_kb = ioc_kb

    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[
            Artefact(
                artefact_id="p1",
                category=ArtefactCategory.RUNNING_PROCESS,
                source_evidence_id="ev-1",
                raw_data={"name": "mimikatz.exe", "CommandLine": "mimikatz.exe sekurlsa"},
            )
        ],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )

    result = await manager.scan_artefacts_against_intel(artefact_set)
    assert result.total_findings >= 2
    assert result.sigma_matches
    assert result.ioc_matches
    assert result.mitre_mappings
    assert result.scan_duration_ms >= 0.0


@pytest.mark.asyncio
async def test_get_intel_summary(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    summary = await manager.get_intel_summary()
    assert "yara_rules_loaded" in summary
    assert "sigma_rules_loaded" in summary
    assert summary["ioc_count"] == 5
    assert summary["mitre_techniques_known"] > 0
