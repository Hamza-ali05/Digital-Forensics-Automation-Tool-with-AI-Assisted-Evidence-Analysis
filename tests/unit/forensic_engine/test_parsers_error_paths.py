"""Focused parser dependency and failure-path tests."""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import ParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers import _tsk_utils
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.memory import _volatility_utils


class StubParser(BaseParser):
    def __init__(self, logger, artefacts=None, error=None, max_artefacts=100):
        super().__init__(logger, max_artefacts=max_artefacts)
        self.artefacts = artefacts or []
        self.error = error

    @property
    def parser_name(self) -> str:
        return "ErrorPathStub"

    def supported_categories(self):
        return [ArtefactCategory.EVENT_LOG]

    def supported_evidence_types(self):
        return [EvidenceType.DISK_IMAGE]

    def _do_parse(self, evidence):
        if self.error:
            raise self.error
        return self.artefacts


def test_safe_import_and_safe_parse_reraise_import_error(
    sample_evidence_image: EvidenceImage, mock_audit_logger: MagicMock
) -> None:
    # Arrange
    parser = StubParser(mock_audit_logger, error=ImportError("optional missing"))

    # Act / Assert
    with pytest.raises(ImportError, match="install optional"):
        parser._safe_import("dfat_module_that_does_not_exist", "install optional")
    with pytest.raises(ImportError, match="optional missing"):
        parser.parse(sample_evidence_image)


def test_generic_exception_is_wrapped_as_parsing_error(
    sample_evidence_image: EvidenceImage, mock_audit_logger: MagicMock
) -> None:
    # Arrange
    parser = StubParser(mock_audit_logger, error=ValueError("corrupt bytes"))

    # Act / Assert
    with pytest.raises(ParsingError, match="corrupt bytes") as exc:
        parser.parse(sample_evidence_image)
    assert exc.value.context["evidence_id"] == sample_evidence_image.evidence_id


def test_artefact_limit_truncates_ten_to_three(
    sample_evidence_image: EvidenceImage, mock_audit_logger: MagicMock
) -> None:
    # Arrange
    artefacts = [
        Artefact(
            artefact_id=f"art-{index}",
            category=ArtefactCategory.EVENT_LOG,
            source_evidence_id=sample_evidence_image.evidence_id,
            raw_data={"index": index},
        )
        for index in range(10)
    ]
    parser = StubParser(mock_audit_logger, artefacts=artefacts, max_artefacts=3)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 3
    assert [item.artefact_id for item in result.artefacts] == [
        "art-0",
        "art-1",
        "art-2",
    ]


@pytest.mark.parametrize(
    ("module_name", "call"),
    [
        ("pytsk3", _tsk_utils.require_pytsk3),
        ("volatility3", _volatility_utils.require_volatility3),
    ],
)
def test_optional_forensic_dependency_import_errors_are_helpful(
    monkeypatch, module_name: str, call
) -> None:
    # Arrange
    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == module_name:
            raise ImportError(f"blocked {module_name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    # Act / Assert
    with pytest.raises(ImportError, match=module_name):
        call()
