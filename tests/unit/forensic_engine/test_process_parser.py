"""Unit tests for ProcessListParser with mocked PluginExecutor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.forensic_engine.parsers.memory.process import ProcessListParser


@pytest.fixture
def memory_evidence(tmp_path: Path, sample_case_metadata: CaseMetadata) -> EvidenceImage:
    """Memory dump evidence wrapper for Volatility parsers."""
    dump = tmp_path / "sample.vmem"
    dump.write_bytes(b"DFAT-FAKE-MEMORY")
    return EvidenceImage(
        evidence_id="ev-mem-process-001",
        file_path=dump,
        evidence_type=EvidenceType.MEMORY_DUMP,
        original_hash="b" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=dump.stat().st_size,
        case=sample_case_metadata,
    )


def test_parse_returns_running_process_artefacts(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify pslist rows map to RUNNING_PROCESS artefacts."""
    # Arrange
    executor = MagicMock()
    executor.execute_plugin = AsyncMock(
        side_effect=[
            [
                {
                    "PID": 1000,
                    "PPID": 4,
                    "ImageFileName": "malware.exe",
                    "CommandLine": "malware.exe -x",
                    "Wow64": "False",
                }
            ],
            [{"PID": 4, "ImageFileName": "System"}],
        ]
    )
    parser = ProcessListParser(executor, mock_audit_logger, run_pstree=True)

    # Act
    result = parser.parse(memory_evidence)

    # Assert
    assert result.total_count == 1
    art = result.artefacts[0]
    assert art.category is ArtefactCategory.RUNNING_PROCESS
    assert art.raw_data["pid"] == 1000
    assert art.raw_data["name"] == "malware.exe"
    assert art.raw_data["parent_name"] == "System"
    assert art.raw_data["command_line"] == "malware.exe -x"


def test_parse_continues_when_pstree_fails(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify pstree enrichment failures do not abort pslist results."""
    # Arrange
    executor = MagicMock()

    async def _execute(path, name, module, evidence_id, config=None):
        if name == "PsTree":
            raise RuntimeError("pstree unavailable")
        return [{"PID": 42, "PPID": 1, "ImageFileName": "cmd.exe"}]

    executor.execute_plugin = AsyncMock(side_effect=_execute)
    parser = ProcessListParser(executor, mock_audit_logger, run_pstree=True)

    # Act
    result = parser.parse(memory_evidence)

    # Assert
    assert result.total_count == 1
    assert result.artefacts[0].raw_data["name"] == "cmd.exe"
    assert result.artefacts[0].raw_data["parent_name"] is None


def test_parse_enforces_artefact_limit(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify process collection respects max_artefacts."""
    # Arrange
    rows = [{"PID": i, "PPID": 0, "ImageFileName": f"p{i}.exe"} for i in range(8)]
    executor = MagicMock()
    executor.execute_plugin = AsyncMock(return_value=rows)
    parser = ProcessListParser(
        executor,
        mock_audit_logger,
        max_artefacts=3,
        run_pstree=False,
    )

    # Act
    result = parser.parse(memory_evidence)

    # Assert
    assert result.total_count == 3


def test_parse_wraps_executor_errors(
    memory_evidence: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify unexpected executor failures become MemoryParsingError."""
    # Arrange
    executor = MagicMock()
    executor.execute_plugin = AsyncMock(side_effect=RuntimeError("vol crash"))
    parser = ProcessListParser(executor, mock_audit_logger, run_pstree=False)

    # Act / Assert
    with pytest.raises(MemoryParsingError, match="ProcessListParser failed"):
        parser.parse(memory_evidence)
    assert parser.supported_evidence_types() == [EvidenceType.MEMORY_DUMP]
    assert parser.supported_categories() == [ArtefactCategory.RUNNING_PROCESS]
