"""Unit tests for RegistryParser with mocked DiskImageAccessor and Registry."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.disk_access import FileEntry
from dfat.forensic_engine.parsers.registry import RegistryParser


def _fake_registry_module(values: list[MagicMock] | None = None) -> SimpleNamespace:
    """Build a minimal fake ``Registry.Registry`` module."""
    value = MagicMock()
    value.name.return_value = "InstallDate"
    value.value.return_value = "12345"
    value.value_type.return_value = "RegSZ"

    root = MagicMock()
    root.path.return_value = "ROOT\\Software"
    root.timestamp.return_value = None
    root.values.return_value = values if values is not None else [value]
    root.subkeys.return_value = []

    registry_instance = MagicMock()
    registry_instance.root.return_value = root

    registry_cls = MagicMock(return_value=registry_instance)
    return SimpleNamespace(
        Registry=registry_cls,
        RegistryKeyNotFoundException=KeyError,
    )


def test_parse_returns_registry_key_artefacts(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify hive walk produces REGISTRY_KEY artefacts."""
    # Arrange
    hive = FileEntry(
        name="SOFTWARE",
        path="/Windows/System32/config/SOFTWARE",
        size=100,
        inode=7,
        file_type="file",
    )
    temp_hive = tmp_path / "SOFTWARE"
    temp_hive.write_bytes(b"hive")
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [hive]
    accessor.extract_file_to_temp.return_value = temp_hive

    fake_mod = _fake_registry_module()
    monkeypatch.setattr(
        RegistryParser,
        "_safe_import",
        lambda self, module_name, install_hint: fake_mod,
    )
    parser = RegistryParser(accessor, mock_audit_logger)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 1
    art = result.artefacts[0]
    assert art.category is ArtefactCategory.REGISTRY_KEY
    assert art.raw_data["hive_name"] == "SOFTWARE"
    assert art.raw_data["value_name"] == "InstallDate"
    assert art.raw_data["value_data"] == "12345"
    accessor.close.assert_called_once()


def test_parse_skips_corrupt_hive(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify corrupt hives are skipped without failing the parse."""
    # Arrange
    hive = FileEntry(
        name="SAM",
        path="/Windows/System32/config/SAM",
        size=50,
        inode=3,
        file_type="file",
    )
    temp_hive = tmp_path / "SAM"
    temp_hive.write_bytes(b"bad")
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [hive]
    accessor.extract_file_to_temp.return_value = temp_hive

    registry_cls = MagicMock(side_effect=RuntimeError("corrupt hive"))
    fake_mod = SimpleNamespace(
        Registry=registry_cls,
        RegistryKeyNotFoundException=KeyError,
    )
    monkeypatch.setattr(
        RegistryParser,
        "_safe_import",
        lambda self, module_name, install_hint: fake_mod,
    )
    parser = RegistryParser(accessor, mock_audit_logger)

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
    """Verify registry value collection respects max_artefacts."""
    # Arrange
    hive = FileEntry(
        name="SYSTEM",
        path="/Windows/System32/config/SYSTEM",
        size=50,
        inode=4,
        file_type="file",
    )
    temp_hive = tmp_path / "SYSTEM"
    temp_hive.write_bytes(b"hive")
    accessor = MagicMock()
    accessor.open_image.return_value = object()
    accessor.get_filesystem.return_value = object()
    accessor.walk_filesystem.return_value = [hive]
    accessor.extract_file_to_temp.return_value = temp_hive

    values = []
    for index in range(5):
        value = MagicMock()
        value.name.return_value = f"v{index}"
        value.value.return_value = f"data{index}"
        value.value_type.return_value = "RegSZ"
        values.append(value)
    monkeypatch.setattr(
        RegistryParser,
        "_safe_import",
        lambda self, module_name, install_hint: _fake_registry_module(values),
    )
    parser = RegistryParser(accessor, mock_audit_logger, max_artefacts=2)

    # Act
    result = parser.parse(sample_evidence_image)

    # Assert
    assert result.total_count == 2


def test_missing_registry_library_raises_import_error(
    sample_evidence_image: EvidenceImage,
    mock_audit_logger: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify missing python-registry surfaces as ImportError."""
    # Arrange
    accessor = MagicMock()
    monkeypatch.setattr(
        RegistryParser,
        "_safe_import",
        lambda self, module_name, install_hint: (_ for _ in ()).throw(
            ImportError(install_hint)
        ),
    )
    parser = RegistryParser(accessor, mock_audit_logger)

    # Act / Assert
    with pytest.raises(ImportError, match="python-registry"):
        parser.parse(sample_evidence_image)
    assert parser.supported_categories() == [ArtefactCategory.REGISTRY_KEY]
    assert parser.supported_evidence_types() == [EvidenceType.DISK_IMAGE]
