"""Unit tests for ArtefactCorrelator."""

from __future__ import annotations

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.processing.correlator import ArtefactCorrelator


def _set(*artefacts: Artefact) -> ArtefactSet:
    """Build an ArtefactSet from artefacts."""
    return ArtefactSet(
        evidence_id="ev-1",
        artefacts=list(artefacts),
        categories_present=sorted({a.category for a in artefacts}, key=lambda c: c.value),
    )


def test_correlate_links_process_and_network_by_pid() -> None:
    """Verify shared PID creates bidirectional process↔network links."""
    # Arrange
    process = Artefact(
        artefact_id="proc-1",
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-1",
        raw_data={"pid": 4242, "name": "chrome.exe"},
    )
    network = Artefact(
        artefact_id="net-1",
        category=ArtefactCategory.NETWORK_CONNECTION,
        source_evidence_id="ev-1",
        raw_data={
            "protocol": "TCP",
            "local_address": "10.0.0.1",
            "remote_address": "1.1.1.1",
            "pid": 4242,
            "is_external": True,
        },
    )

    # Act
    result = ArtefactCorrelator().correlate(_set(process, network))

    # Assert
    by_id = {a.artefact_id: a for a in result.artefacts}
    assert "net-1" in by_id["proc-1"].metadata["correlated_artefact_ids"]
    assert "proc-1" in by_id["net-1"].metadata["correlated_artefact_ids"]


def test_correlate_links_process_and_injection() -> None:
    """Verify shared PID links process↔injected code."""
    # Arrange
    process = Artefact(
        artefact_id="proc-2",
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-1",
        raw_data={"pid": 99, "name": "bad.exe"},
    )
    injected = Artefact(
        artefact_id="inj-1",
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={
            "pid": 99,
            "process_name": "bad.exe",
            "vad_start": "0x1",
            "protection": "PAGE_EXECUTE_READWRITE",
            "suspicious_indicators": ["MZ header"],
        },
    )

    # Act
    result = ArtefactCorrelator().correlate(_set(process, injected))

    # Assert
    by_id = {a.artefact_id: a for a in result.artefacts}
    assert "inj-1" in by_id["proc-2"].metadata["correlated_artefact_ids"]


def test_correlate_links_registry_path_to_filesystem() -> None:
    """Verify registry value paths link to filesystem artefacts."""
    # Arrange
    registry = Artefact(
        artefact_id="reg-1",
        category=ArtefactCategory.REGISTRY_KEY,
        source_evidence_id="ev-1",
        raw_data={
            "hive_name": "SOFTWARE",
            "key_path": r"CurrentVersion\Run",
            "value_name": "App",
            "value_data": r"C:\Windows\Temp\tool.exe",
            "value_type": "RegSZ",
        },
    )
    filesystem = Artefact(
        artefact_id="fs-1",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id="ev-1",
        raw_data={
            "filename": "tool.exe",
            "path": r"/Windows/Temp/tool.exe",
            "size": 10,
            "is_deleted": False,
            "file_type": "file",
        },
    )

    # Act
    result = ArtefactCorrelator().correlate(_set(registry, filesystem))

    # Assert
    by_id = {a.artefact_id: a for a in result.artefacts}
    assert "fs-1" in by_id["reg-1"].metadata["correlated_artefact_ids"]


def test_correlate_empty_set_passthrough() -> None:
    """Verify empty artefact sets are returned unchanged."""
    # Arrange
    empty = ArtefactSet(evidence_id="ev-1", artefacts=[], categories_present=[])

    # Act
    result = ArtefactCorrelator().correlate(empty)

    # Assert
    assert result.total_count == 0
    assert result.evidence_id == "ev-1"
