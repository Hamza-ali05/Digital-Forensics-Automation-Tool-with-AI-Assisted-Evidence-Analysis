"""System-wide constants for the DFAT pipeline."""

from __future__ import annotations

from dfat.core.enums import HashAlgorithm

DFAT_VERSION = "0.1.0"
SUPPORTED_DISK_EXTENSIONS = frozenset({".dd", ".raw", ".e01", ".img", ".001"})
SUPPORTED_MEMORY_EXTENSIONS = frozenset({".raw", ".vmem", ".dmp", ".mem"})
DEFAULT_HASH_ALGORITHM = HashAlgorithm.SHA256
JSON_SCHEMA_VERSION = "1.0.0"
MAX_ARTEFACTS_PER_CATEGORY = 10000
AUDIT_LOG_FILENAME = "audit_trail.jsonl"
