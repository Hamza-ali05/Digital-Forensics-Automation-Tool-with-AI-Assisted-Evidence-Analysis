"""Unit tests for NetworkArtefactParser with mocked PluginExecutor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.forensic_engine.parsers.memory.network import NetworkArtefactParser


@pytest.fixture
def memory_evidence(tmp_path: Path, sample_case_metadata: CaseMetadata) -> EvidenceImage:
    """Memory dump evidence wrapper for network parser tests."""
    dump = tmp_path / "sample.vmem"
    dump.write_bytes(b"DFAT-FAKE-MEMORY")
    return EvidenceImage(
        evidence_id="ev-mem-net-001",
        file_path=dump,
        evidence_type=EvidenceType.MEMORY_DUMP,
        original_hash="c" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=dump.stat().st_size,
        case=sample_case_metadata,
    )


def test_parse_returns_network_connection_artefacts(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify netscan rows map to NETWORK_CONNECTION artefacts."""
    # Arrange
    executor = MagicMock()
    executor.execute_plugin = AsyncMock(
        return_value=[
            {
                "Proto": "TCPv4",
                "LocalAddr": "10.0.0.5",
                "LocalPort": 445,
                "ForeignAddr": "8.8.8.8",
                "ForeignPort": 53,
                "State": "ESTABLISHED",
                "PID": 1234,
                "Owner": "chrome.exe",
            }
        ]
    )
    parser = NetworkArtefactParser(executor, mock_audit_logger)

    # Act
    result = parser.parse(memory_evidence)

    # Assert
    assert result.total_count == 1
    art = result.artefacts[0]
    assert art.category is ArtefactCategory.NETWORK_CONNECTION
    assert art.raw_data["remote_address"] == "8.8.8.8"
    assert art.raw_data["is_external"] is True
    assert art.raw_data["owner_process"] == "chrome.exe"
    assert art.raw_data["protocol"] == "TCPv4"


def test_is_external_detects_private_addresses(mock_audit_logger: MagicMock) -> None:
    """Verify private/loopback addresses are not marked external."""
    # Arrange
    parser = NetworkArtefactParser(MagicMock(), mock_audit_logger)

    # Act / Assert
    assert parser._is_external("192.168.1.10") is False  # noqa: SLF001
    assert parser._is_external("127.0.0.1") is False  # noqa: SLF001
    assert parser._is_external("1.1.1.1") is True  # noqa: SLF001
    assert parser._is_external(None) is False  # noqa: SLF001


def test_parse_enforces_artefact_limit(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify network collection respects max_artefacts."""
    # Arrange
    rows = [
        {
            "Proto": "UDP",
            "LocalAddr": "0.0.0.0",
            "LocalPort": i,
            "ForeignAddr": "1.2.3.4",
            "ForeignPort": 80,
            "State": "",
            "PID": i,
            "Owner": "svc",
        }
        for i in range(6)
    ]
    executor = MagicMock()
    executor.execute_plugin = AsyncMock(return_value=rows)
    parser = NetworkArtefactParser(executor, mock_audit_logger, max_artefacts=2)

    # Act
    result = parser.parse(memory_evidence)

    # Assert
    assert result.total_count == 2


def test_parse_wraps_executor_errors(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify unexpected executor failures become MemoryParsingError."""
    # Arrange
    executor = MagicMock()
    executor.execute_plugin = AsyncMock(side_effect=RuntimeError("netscan failed"))
    parser = NetworkArtefactParser(executor, mock_audit_logger)

    # Act / Assert
    with pytest.raises(MemoryParsingError, match="NetworkArtefactParser failed"):
        parser.parse(memory_evidence)
    assert parser.supported_categories() == [ArtefactCategory.NETWORK_CONNECTION]
    assert parser.supported_evidence_types() == [EvidenceType.MEMORY_DUMP]
