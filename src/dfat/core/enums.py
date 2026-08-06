"""DFAT domain enumerations shared across all engines."""

from __future__ import annotations

from enum import Enum


class EvidenceType(str, Enum):
    """Type of forensic evidence under analysis."""

    DISK_IMAGE = "disk_image"
    MEMORY_DUMP = "memory_dump"


class ArtefactCategory(str, Enum):
    """Category of extracted forensic artefact."""

    FILESYSTEM_METADATA = "filesystem_metadata"
    REGISTRY_KEY = "registry_key"
    BROWSER_HISTORY = "browser_history"
    EVENT_LOG = "event_log"
    RUNNING_PROCESS = "running_process"
    NETWORK_CONNECTION = "network_connection"
    INJECTED_CODE = "injected_code"


class PipelineStage(str, Enum):
    """Five-stage forensic processing pipeline stages."""

    ACQUISITION = "acquisition"
    PARSING = "parsing"
    AI_TRIAGE = "ai_triage"
    REPORTING = "reporting"
    EVALUATION = "evaluation"


class SuspicionLevel(str, Enum):
    """Suspicion classification assigned during AI triage."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class ReportFormat(str, Enum):
    """Supported forensic report output formats."""

    JSON = "json"
    NARRATIVE = "narrative"
    DUAL = "dual"


class HashAlgorithm(str, Enum):
    """Supported cryptographic hash algorithms for integrity checks."""

    SHA256 = "sha256"
    MD5 = "md5"
    SHA1 = "sha1"
