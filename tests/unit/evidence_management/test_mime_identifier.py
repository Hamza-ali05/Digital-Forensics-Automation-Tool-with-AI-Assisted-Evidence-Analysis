"""Unit tests for MIMEIdentifier."""

from __future__ import annotations

from pathlib import Path

from dfat.core.enums import EvidenceType
from dfat.evidence_management.mime_identifier import (
    EXTENSION_MIME_MAP,
    MIMEIdentifier,
)


def test_extension_mapping() -> None:
    """Known forensic extensions map to expected MIME types."""
    # Arrange
    identifier = MIMEIdentifier()

    # Act / Assert
    assert identifier.identify_from_extension(Path("disk.e01")) == "application/x-e01"
    assert EXTENSION_MIME_MAP[".dd"] == "application/octet-stream"
    assert EXTENSION_MIME_MAP[".vmem"] == "application/x-vmem"


def test_fallback_unknown_extension(tmp_path: Path) -> None:
    """Unknown extensions fall back to octet-stream or stdlib guess."""
    # Arrange
    identifier = MIMEIdentifier()
    path = tmp_path / "mystery.xyz"

    # Act
    mime = identifier.identify_from_extension(path)

    # Assert
    assert isinstance(mime, str)
    assert mime


def test_forensic_image_valid() -> None:
    """Disk image MIME/extension combinations are accepted."""
    # Arrange
    identifier = MIMEIdentifier()

    # Act / Assert
    assert identifier.is_forensic_image(
        "application/octet-stream",
        ".dd",
        evidence_type=EvidenceType.DISK_IMAGE,
    )
    assert identifier.is_forensic_image(
        "application/x-e01",
        ".e01",
        evidence_type=EvidenceType.DISK_IMAGE,
    )


def test_forensic_image_invalid() -> None:
    """Non-forensic combinations are rejected."""
    # Arrange
    identifier = MIMEIdentifier()

    # Act / Assert
    assert not identifier.is_forensic_image(
        "text/plain",
        ".txt",
        evidence_type=EvidenceType.DISK_IMAGE,
    )


def test_identify_returns_method(tmp_path: Path) -> None:
    """identify returns mime type and detection method."""
    # Arrange
    identifier = MIMEIdentifier()
    path = tmp_path / "sample.dd"
    path.write_bytes(b"\x00" * 64)

    # Act
    mime, method = identifier.identify(path)

    # Assert
    assert mime
    assert method in {"magic", "extension", "stdlib_mimetypes"}
