"""Pipeline job, stage, and parser status enumerations."""

from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    """Lifecycle status for a scheduled pipeline job."""

    QUEUED = "queued"
    INITIALISING = "initialising"
    RUNNING = "running"
    STAGE_COMPLETE = "stage_complete"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class StageStatus(str, Enum):
    """Execution status for a single pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ParserStatus(str, Enum):
    """Availability and execution status for an artefact parser."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
