"""Shared cryptographic hashing utilities for evidential integrity."""

from __future__ import annotations

import hashlib
from pathlib import Path

from dfat.core.enums import HashAlgorithm
from dfat.core.exceptions import IntegrityVerificationError

_CHUNK_SIZE = 8192

_HASHLIB_NAMES: dict[HashAlgorithm, str] = {
    HashAlgorithm.SHA256: "sha256",
    HashAlgorithm.MD5: "md5",
    HashAlgorithm.SHA1: "sha1",
}


def compute_file_hash(file_path: Path, algorithm: HashAlgorithm) -> str:
    """Compute a cryptographic hash of a file using chunked reads.

    Args:
        file_path: Path to the file to hash.
        algorithm: Hash algorithm to use.

    Returns:
        Lowercase hexadecimal digest string.
    """
    hasher = hashlib.new(_HASHLIB_NAMES[algorithm])
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_data_hash(data: bytes, algorithm: HashAlgorithm) -> str:
    """Compute a cryptographic hash of an in-memory byte payload.

    Args:
        data: Bytes to hash.
        algorithm: Hash algorithm to use.

    Returns:
        Lowercase hexadecimal digest string.
    """
    hasher = hashlib.new(_HASHLIB_NAMES[algorithm])
    hasher.update(data)
    return hasher.hexdigest()


def verify_hash(
    file_path: Path,
    expected_hash: str,
    algorithm: HashAlgorithm,
) -> bool:
    """Verify a file hash against an expected digest.

    Args:
        file_path: Path to the file to verify.
        expected_hash: Expected hexadecimal digest.
        algorithm: Hash algorithm used for verification.

    Returns:
        True if the computed hash matches ``expected_hash``.

    Raises:
        IntegrityVerificationError: If the computed hash does not match.
    """
    actual_hash = compute_file_hash(file_path, algorithm)
    if actual_hash.lower() != expected_hash.lower():
        raise IntegrityVerificationError(
            f"Integrity verification failed for {file_path}",
            expected_hash=expected_hash.lower(),
            actual_hash=actual_hash.lower(),
            context={"path": str(file_path), "algorithm": algorithm.value},
        )
    return True
