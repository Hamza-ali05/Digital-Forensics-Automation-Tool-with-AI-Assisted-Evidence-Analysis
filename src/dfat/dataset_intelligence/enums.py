"""Dataset intelligence enumerations."""

from __future__ import annotations

from enum import Enum


class DatasetCategory(str, Enum):
    """Logical dataset purpose within the DFAT extension architecture."""

    BENCHMARK = "benchmark"
    FORENSIC_OPERATIONAL = "forensic_operational"
    AI_KNOWLEDGE = "ai_knowledge"
    THREAT_INTELLIGENCE = "threat_intelligence"
    MACHINE_LEARNING = "machine_learning"
    FORENSIC_CHALLENGE = "forensic_challenge"
    USER_UPLOADED = "user_uploaded"


class DatasetFormat(str, Enum):
    """Supported dataset file and bundle formats."""

    DISK_IMAGE = "disk_image"
    MEMORY_DUMP = "memory_dump"
    PCAP = "pcap"
    EVTX = "evtx"
    REGISTRY_HIVE = "registry_hive"
    SQLITE_DB = "sqlite_db"
    CSV = "csv"
    JSON = "json"
    XML = "xml"
    YARA_RULES = "yara_rules"
    SIGMA_RULES = "sigma_rules"
    STIX_BUNDLE = "stix_bundle"
    PLAIN_TEXT = "plain_text"
    BINARY = "binary"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


class DatasetStatus(str, Enum):
    """Lifecycle state of a dataset inside the intelligence subsystem."""

    DISCOVERED = "discovered"
    VALIDATING = "validating"
    VALIDATED = "validated"
    INDEXING = "indexing"
    INDEXED = "indexed"
    PREPROCESSING = "preprocessing"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


class IndexingStatus(str, Enum):
    """Indexing state for retrieval-oriented dataset processing."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    STALE = "stale"
