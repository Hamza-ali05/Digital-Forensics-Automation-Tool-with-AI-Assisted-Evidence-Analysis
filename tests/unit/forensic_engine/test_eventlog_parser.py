"""Unit tests for EventLogParser with mocked DiskImageAccessor and Evtx."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.disk_access import FileEntry
from dfat.forensic_engine.parsers.eventlog import EventLogParser

_SAMPLE_XML = """
<Event>
  <System>
    <Provider Name="Microsoft-Windows-Security-Auditing"/>
    <EventID>4624</EventID>
    <Level>0</Level>
    <Channel>Security</Channel>
    <Computer>WORKSTATION1</Computer>
  </System>
  <EventData>
    <Data Name="TargetUserName">alice</Data>
    <Data Name="LogonType">2</Data>
  </EventData>
</Event>
"""


def _fake_evtx_module(xml: str = _SAMPLE_XML) -> SimpleNamespace:
    """Build a minimal fake ``Evtx.Evtx`` module."""
    record = MagicMock()
    record.xml.return_value = xml
    record.timestamp.return_value = None

    evtx_cm = MagicMock()
    evtx_cm.__enter__.return_value = evtx_cm
    evtx_cm.__exit__.return_value = False
    evtx_cm.records.return_value = [record]

    evtx_cls = MagicMock(return_value=evtx_cm)
    return SimpleNamespace(Evtx=evtx_cls)


def test_parse_returns_event_log_artefacts(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify EVTX records become EVENT_LOG artefacts with security flags."""
    # Arrange
    evtx_path = tmp_path / "Security.evtx"
    evtx_path.write_bytes(b"evtx")
    entry = FileEntry(
        name="Security.evtx",
        path="/Windows/System32/winevt/Logs/Security.evtx",
        size=10,
        inode=21,
        file_type="file",
    )
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [entry]
    accessor.extract_file_to_temp.return_value = evtx_path
    monkeypatch.setattr(
        EventLogParser,
        "_safe_import",
        lambda self, module_name, install_hint: _fake_evtx_module(),
    )
    parser = EventLogParser(accessor, mock_audit_logger)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 1
    art = result.artefacts[0]
    assert art.category is ArtefactCategory.EVENT_LOG
    assert art.raw_data["event_id"] == 4624
    assert art.raw_data["channel"] == "Security"
    assert art.raw_data["is_security_relevant"] is True
    assert art.raw_data["event_data"]["TargetUserName"] == "alice"


def test_parse_skips_corrupt_evtx(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify corrupt EVTX files are skipped after warning."""
    # Arrange
    evtx_path = tmp_path / "broken.evtx"
    evtx_path.write_bytes(b"bad")
    entry = FileEntry(
        name="broken.evtx",
        path="/Windows/System32/winevt/Logs/broken.evtx",
        size=3,
        inode=22,
        file_type="file",
    )
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [entry]
    accessor.extract_file_to_temp.return_value = evtx_path

    evtx_cls = MagicMock(side_effect=RuntimeError("bad evtx"))
    monkeypatch.setattr(
        EventLogParser,
        "_safe_import",
        lambda self, module_name, install_hint: SimpleNamespace(Evtx=evtx_cls),
    )
    parser = EventLogParser(accessor, mock_audit_logger)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 0


def test_parse_enforces_artefact_limit(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify event collection respects max_artefacts."""
    # Arrange
    evtx_path = tmp_path / "Security.evtx"
    evtx_path.write_bytes(b"evtx")
    entry = FileEntry(
        name="Security.evtx",
        path="/Windows/System32/winevt/Logs/Security.evtx",
        size=10,
        inode=23,
        file_type="file",
    )
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [entry]
    accessor.extract_file_to_temp.return_value = evtx_path

    records = []
    for event_id in (4624, 4625, 4688, 7045):
        record = MagicMock()
        record.xml.return_value = (
            f"<Event><System><EventID>{event_id}</EventID>"
            f"<Channel>Security</Channel></System></Event>"
        )
        record.timestamp.return_value = None
        records.append(record)
    evtx_cm = MagicMock()
    evtx_cm.__enter__.return_value = evtx_cm
    evtx_cm.__exit__.return_value = False
    evtx_cm.records.return_value = records
    fake = SimpleNamespace(Evtx=MagicMock(return_value=evtx_cm))
    monkeypatch.setattr(
        EventLogParser,
        "_safe_import",
        lambda self, module_name, install_hint: fake,
    )
    parser = EventLogParser(accessor, mock_audit_logger, max_artefacts=2)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 2


def test_missing_evtx_library_raises_import_error(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify missing python-evtx surfaces as ImportError."""
    # Arrange
    accessor = MagicMock()
    monkeypatch.setattr(
        EventLogParser,
        "_safe_import",
        lambda self, module_name, install_hint: (_ for _ in ()).throw(
            ImportError(install_hint)
        ),
    )
    parser = EventLogParser(accessor, mock_audit_logger)

    # Act / Assert
    with pytest.raises(ImportError, match="python-evtx"):
        parser.parse(sample_evidence_image)
    assert parser.parser_name == "EventLogParser"
    assert parser.supported_categories() == [ArtefactCategory.EVENT_LOG]
    assert parser.supported_evidence_types() == [EvidenceType.DISK_IMAGE]
