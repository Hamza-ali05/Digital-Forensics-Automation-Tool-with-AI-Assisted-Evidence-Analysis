"""Unit tests for IOCDetector."""

from __future__ import annotations

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.processing.ioc_detector import IOCDetector


def _set(*artefacts: Artefact) -> ArtefactSet:
    """Build an ArtefactSet from artefacts."""
    return ArtefactSet(
        evidence_id="ev-1",
        artefacts=list(artefacts),
        categories_present=sorted({a.category for a in artefacts}, key=lambda c: c.value),
    )


def test_detect_suspicious_process_name() -> None:
    """Verify mimikatz-like process names produce high-confidence IOCs."""
    # Arrange
    artefact = Artefact(
        artefact_id="p1",
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-1",
        raw_data={"pid": 1, "name": "mimikatz.exe"},
    )

    # Act
    matches = IOCDetector().detect(_set(artefact))

    # Assert
    assert matches
    assert any(m.ioc_type == "suspicious_process" for m in matches)
    assert any(m.confidence == "high" for m in matches)


def test_detect_suspicious_registry_path() -> None:
    """Verify Run key paths are flagged."""
    # Arrange
    artefact = Artefact(
        artefact_id="r1",
        category=ArtefactCategory.REGISTRY_KEY,
        source_evidence_id="ev-1",
        raw_data={
            "hive_name": "SOFTWARE",
            "key_path": r"Microsoft\Windows\CurrentVersion\Run\Evil",
            "value_name": "Evil",
            "value_data": "evil.exe",
            "value_type": "RegSZ",
        },
    )

    # Act
    matches = IOCDetector().detect(_set(artefact))

    # Assert
    assert any(m.ioc_type == "suspicious_registry" for m in matches)


def test_detect_suspicious_extension_and_deleted_file() -> None:
    """Verify suspicious extensions on deleted files are flagged."""
    # Arrange
    artefact = Artefact(
        artefact_id="f1",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id="ev-1",
        raw_data={
            "filename": "payload.ps1",
            "path": "/Temp/payload.ps1",
            "size": 10,
            "is_deleted": True,
            "file_type": "deleted",
        },
    )

    # Act
    matches = IOCDetector().detect(_set(artefact))

    # Assert
    assert matches
    assert any("ps1" in m.indicator.lower() or "deleted" in m.description.lower() for m in matches)


def test_detect_external_network_and_malicious_port() -> None:
    """Verify external connections and known ports produce network IOCs."""
    # Arrange
    artefact = Artefact(
        artefact_id="n1",
        category=ArtefactCategory.NETWORK_CONNECTION,
        source_evidence_id="ev-1",
        raw_data={
            "protocol": "TCP",
            "local_address": "10.0.0.2",
            "remote_address": "8.8.8.8",
            "remote_port": 4444,
            "is_external": True,
        },
    )

    # Act
    matches = IOCDetector().detect(_set(artefact))

    # Assert
    assert matches
    assert any(
        m.ioc_type in {"suspicious_port", "external_connection"} for m in matches
    )


def test_detect_injected_code_and_ignores_browser() -> None:
    """Verify injected code always matches and browser history yields none."""
    # Arrange
    injected = Artefact(
        artefact_id="i1",
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={
            "pid": 9,
            "process_name": "x.exe",
            "vad_start": "0x1",
            "protection": "PAGE_EXECUTE_READWRITE",
            "suspicious_indicators": ["MZ header"],
        },
    )
    browser = Artefact(
        artefact_id="b1",
        category=ArtefactCategory.BROWSER_HISTORY,
        source_evidence_id="ev-1",
        raw_data={
            "url": "https://example.com",
            "title": "Example",
            "visit_count": 1,
            "browser_type": "chrome",
        },
    )

    # Act
    matches = IOCDetector().detect(_set(injected, browser))

    # Assert
    assert any(m.artefact_id == "i1" for m in matches)
    assert all(m.artefact_id != "b1" for m in matches)
