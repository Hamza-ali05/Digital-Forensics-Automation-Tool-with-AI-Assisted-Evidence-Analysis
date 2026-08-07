"""Unit tests for CodeInjectionParser with mocked PluginExecutor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.forensic_engine.parsers.memory.injection import CodeInjectionParser


@pytest.fixture
def memory_evidence(tmp_path: Path, sample_case_metadata: CaseMetadata) -> EvidenceImage:
    """Memory dump evidence wrapper for injection parser tests."""
    dump = tmp_path / "sample.vmem"
    dump.write_bytes(b"DFAT-FAKE-MEMORY")
    return EvidenceImage(
        evidence_id="ev-mem-inj-001",
        file_path=dump,
        evidence_type=EvidenceType.MEMORY_DUMP,
        original_hash="d" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=dump.stat().st_size,
        case=sample_case_metadata,
    )


def test_parse_returns_injected_code_artefacts(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify malfind rows map to INJECTED_CODE artefacts with indicators."""
    # Arrange
    executor = MagicMock()
    executor.execute_plugin = AsyncMock(
        return_value=[
            {
                "PID": 999,
                "Process": "suspicious.exe",
                "Start VPN": "0x10000000",
                "End VPN": "0x10001000",
                "Tag": "VadS",
                "Protection": "PAGE_EXECUTE_READWRITE",
                "Hexdump": "4d5a900003000000",  # MZ header
            }
        ]
    )
    parser = CodeInjectionParser(executor, mock_audit_logger)

    # Act
    result = parser.parse(memory_evidence)

    # Assert
    assert result.total_count == 1
    art = result.artefacts[0]
    assert art.category is ArtefactCategory.INJECTED_CODE
    assert art.raw_data["pid"] == 999
    assert art.raw_data["process_name"] == "suspicious.exe"
    assert "MZ header" in art.raw_data["suspicious_indicators"]
    assert "RWX memory region" in art.raw_data["suspicious_indicators"]


def test_parse_enforces_artefact_limit(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify injection collection respects max_artefacts."""
    # Arrange
    rows = [
        {
            "PID": i,
            "Process": f"p{i}.exe",
            "Start VPN": hex(i),
            "End VPN": hex(i + 1),
            "Protection": "PAGE_READWRITE",
            "Hexdump": "90909090",
        }
        for i in range(5)
    ]
    executor = MagicMock()
    executor.execute_plugin = AsyncMock(return_value=rows)
    parser = CodeInjectionParser(executor, mock_audit_logger, max_artefacts=2)

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
    executor.execute_plugin = AsyncMock(side_effect=RuntimeError("malfind boom"))
    parser = CodeInjectionParser(executor, mock_audit_logger)

    # Act / Assert
    with pytest.raises(MemoryParsingError, match="CodeInjectionParser failed"):
        parser.parse(memory_evidence)
    assert parser.supported_categories() == [ArtefactCategory.INJECTED_CODE]
    assert parser.supported_evidence_types() == [EvidenceType.MEMORY_DUMP]
