"""DFAT Forensic Pipeline — Orchestration, scheduling, and monitoring."""

from __future__ import annotations

from typing import Any

from dfat.pipeline.enums import JobStatus, ParserStatus, StageStatus
from dfat.pipeline.models import (
    ParserResult,
    PipelineJob,
    PipelineProgress,
    StageExecution,
)
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.pipeline.stage_registry import StageRegistry
from dfat.pipeline.job_manager import JobCancellationError, JobManager, JobNotFoundError
from dfat.pipeline.job_runner import JobRunner
from dfat.pipeline.pipeline_logger import PipelineLogger
from dfat.pipeline.progress_tracker import ProgressNotFoundError, ProgressTracker
from dfat.pipeline.error_handler import PipelineErrorHandler
from dfat.pipeline.evidence_discovery import DiscoveredEvidence, EvidenceDiscoveryService
from dfat.pipeline.evidence_loader import EvidenceLoader, LoadedEvidence
from dfat.pipeline.evidence_router import EvidenceRouter
from dfat.pipeline.exceptions import (
    AllParsersFailedError,
    ParserUnavailableError,
    PipelineCancelledError,
    PipelineError,
    PipelineJobNotFoundError,
    PipelineStageError,
    PipelineTimeoutError,
)
from dfat.pipeline.parser_registry import ParserRegistry

# PipelineOrchestrator is imported lazily — it pulls database repositories that
# import ``dfat.pipeline.models``, which would otherwise circular-import this package.

__all__ = [
    "AllParsersFailedError",
    "DiscoveredEvidence",
    "EvidenceDiscoveryService",
    "EvidenceLoader",
    "EvidenceRouter",
    "IPipelineStage",
    "JobCancellationError",
    "JobManager",
    "JobNotFoundError",
    "JobRunner",
    "JobStatus",
    "LoadedEvidence",
    "ParserRegistry",
    "ParserResult",
    "ParserStatus",
    "ParserUnavailableError",
    "PipelineCancelledError",
    "PipelineContext",
    "PipelineError",
    "PipelineErrorHandler",
    "PipelineJob",
    "PipelineJobNotFoundError",
    "PipelineLogger",
    "PipelineOrchestrator",
    "PipelineProgress",
    "PipelineStageError",
    "PipelineTimeoutError",
    "ProgressNotFoundError",
    "ProgressTracker",
    "StageExecution",
    "StageRegistry",
    "StageStatus",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve symbols that would otherwise create import cycles."""
    if name == "PipelineOrchestrator":
        from dfat.pipeline.orchestrator import PipelineOrchestrator

        return PipelineOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
