"""Unit tests for BaseParser template-method helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import ParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser


class _StubParser(BaseParser):
    """Concrete BaseParser for unit tests."""

    def __init__(
        self,
        audit_logger: MagicMock,
        max_artefacts: int = 100,
        *,
        artefacts: list[Artefact] | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__(audit_logger=audit_logger, max_artefacts=max_artefacts)
        self._artefacts = artefacts or []
        self._error = error

    @property
    def parser_name(self) -> str:
        return "StubParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        return [ArtefactCategory.FILESYSTEM_METADATA]

    def supported_evidence_types(self) -> list[EvidenceType]:
        return [EvidenceType.DISK_IMAGE]

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        if self._error is not None:
            raise self._error
        return list(self._artefacts)


def _make_artefacts(count: int, evidence_id: str) -> list[Artefact]:
    """Create ``count`` artefacts for truncation tests."""
    return [
        Artefact(
            category=ArtefactCategory.FILESYSTEM_METADATA,
            source_evidence_id=evidence_id,
            raw_data={"n": index},
        )
        for index in range(count)
    ]


def test_parse_logs_start_and_complete(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify parse audits start/complete around a successful _do_parse."""
    # Arrange
    artefacts = _make_artefacts(2, sample_evidence_image.evidence_id)
    parser = _StubParser(mock_audit_logger, artefacts=artefacts)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 2
    actions = [call.kwargs.get("action") for call in mock_audit_logger.log_action.call_args_list]
    assert "PARSE_START" in actions
    assert "PARSE_COMPLETE" in actions


def test_parse_truncates_to_max_artefacts(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify _truncate enforces the configured artefact cap."""
    # Arrange
    artefacts = _make_artefacts(10, sample_evidence_image.evidence_id)
    parser = _StubParser(mock_audit_logger, max_artefacts=4, artefacts=artefacts)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 4


def test_parse_wraps_unexpected_errors(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify unexpected exceptions become ParsingError with PARSE_ERROR audit."""
    # Arrange
    parser = _StubParser(mock_audit_logger, error=RuntimeError("boom"))

    # Act / Assert
    with pytest.raises(ParsingError, match="StubParser failed"):
        parser.parse(sample_evidence_image)
    assert any(
        call.kwargs.get("action") == "PARSE_ERROR"
        for call in mock_audit_logger.log_action.call_args_list
    )


def test_safe_parse_rethrows_import_error(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
) -> None:
    """Verify ImportError from _do_parse is not wrapped."""
    # Arrange
    parser = _StubParser(mock_audit_logger, error=ImportError("missing lib"))

    # Act / Assert
    with pytest.raises(ImportError, match="missing lib"):
        parser.parse(sample_evidence_image)


def test_create_artefact_and_check_limit(mock_audit_logger: MagicMock) -> None:
    """Verify artefact factory and limit helper behaviour."""
    # Arrange
    parser = _StubParser(mock_audit_logger, max_artefacts=2)

    # Act
    artefact = parser._create_artefact(  # noqa: SLF001
        category=ArtefactCategory.FILESYSTEM_METADATA,
        raw_data={"ok": True},
        evidence_id="ev-1",
        source_path="/a/b",
    )

    # Assert
    assert artefact.category is ArtefactCategory.FILESYSTEM_METADATA
    assert artefact.source_path == "/a/b"
    assert artefact.metadata["parser"] == "StubParser"
    assert parser._check_limit(0) is True  # noqa: SLF001
    assert parser._check_limit(1) is True  # noqa: SLF001
    assert parser._check_limit(2) is False  # noqa: SLF001
    assert parser._safe_import("json", "hint") is not None  # noqa: SLF001
    with pytest.raises(ImportError, match="hint"):
        parser._safe_import("dfat_missing_module_xyz", "hint")  # noqa: SLF001
