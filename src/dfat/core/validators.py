"""Domain input validators for evidence paths and integrity hashes."""

from __future__ import annotations

import re
from pathlib import Path

from dfat.core.enums import HashAlgorithm
from dfat.core.exceptions import EvidenceNotFoundError

SUPPORTED_DISK_EXTENSIONS: set[str] = {".dd", ".raw", ".e01", ".img", ".001"}
SUPPORTED_MEMORY_EXTENSIONS: set[str] = {".raw", ".vmem", ".dmp", ".mem"}

_HASH_LENGTHS: dict[HashAlgorithm, int] = {
    HashAlgorithm.MD5: 32,
    HashAlgorithm.SHA1: 40,
    HashAlgorithm.SHA256: 64,
}
_HEX_PATTERN = re.compile(r"^[a-fA-F0-9]+$")


def validate_hash_format(hash_string: str, algorithm: HashAlgorithm) -> bool:
    """Validate that a hash string matches the expected format for an algorithm.

    Args:
        hash_string: Candidate hexadecimal hash digest.
        algorithm: Hash algorithm that defines expected digest length.

    Returns:
        True if the hash string is valid for ``algorithm``; otherwise False.
    """
    expected_length = _HASH_LENGTHS[algorithm]
    if len(hash_string) != expected_length:
        return False
    return _HEX_PATTERN.fullmatch(hash_string) is not None


def validate_evidence_path(path: Path) -> Path:
    """Validate that an evidence path exists and refers to a file.

    Args:
        path: Candidate evidence filesystem path.

    Returns:
        The validated path.

    Raises:
        EvidenceNotFoundError: If the path does not exist or is not a file.
    """
    if not path.exists() or not path.is_file():
        raise EvidenceNotFoundError(
            f"Evidence path not found or not a file: {path}",
            context={"path": str(path)},
        )
    return path


def validate_file_extension(path: Path, allowed: set[str]) -> bool:
    """Validate that a path extension is within an allowed set.

    Args:
        path: Candidate filesystem path.
        allowed: Allowed extensions including the leading dot (case-insensitive).

    Returns:
        True if the path extension is allowed; otherwise False.
    """
    normalised_allowed = {ext.lower() for ext in allowed}
    return path.suffix.lower() in normalised_allowed
