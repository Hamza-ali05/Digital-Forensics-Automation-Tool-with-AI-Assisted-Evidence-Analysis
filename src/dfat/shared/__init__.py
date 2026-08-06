"""DFAT Shared — Cross-cutting hashing, timing, and constants utilities."""

from dfat.shared.constants import (
    AUDIT_LOG_FILENAME,
    DEFAULT_HASH_ALGORITHM,
    DFAT_VERSION,
    JSON_SCHEMA_VERSION,
    MAX_ARTEFACTS_PER_CATEGORY,
    SUPPORTED_DISK_EXTENSIONS,
    SUPPORTED_MEMORY_EXTENSIONS,
)
from dfat.shared.hashing import compute_data_hash, compute_file_hash, verify_hash
from dfat.shared.timing import PerformanceTimer

__all__ = [
    "AUDIT_LOG_FILENAME",
    "DEFAULT_HASH_ALGORITHM",
    "DFAT_VERSION",
    "JSON_SCHEMA_VERSION",
    "MAX_ARTEFACTS_PER_CATEGORY",
    "PerformanceTimer",
    "SUPPORTED_DISK_EXTENSIONS",
    "SUPPORTED_MEMORY_EXTENSIONS",
    "compute_data_hash",
    "compute_file_hash",
    "verify_hash",
]
