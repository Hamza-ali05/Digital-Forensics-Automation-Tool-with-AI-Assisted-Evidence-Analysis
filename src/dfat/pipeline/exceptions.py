"""Pipeline-specific exceptions extending the DFAT domain error hierarchy."""

from __future__ import annotations

from typing import Any, Optional, Union

from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.exceptions import DFATError


class PipelineError(DFATError):
    """Base error for forensic pipeline scheduling and execution failures."""


class PipelineJobNotFoundError(PipelineError):
    """Raised when a pipeline job identifier cannot be resolved.

    Args:
        message: Human-readable error description.
        job_id: Missing job identifier.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        job_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["job_id"] = job_id
        self.job_id = job_id
        super().__init__(message, context=details)


class PipelineStageError(PipelineError):
    """Raised when a pipeline stage fails during execution.

    Args:
        message: Human-readable error description.
        stage: Pipeline stage that failed.
        original_error: Underlying exception (or its message).
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: PipelineStage,
        original_error: Union[BaseException, str],
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["stage"] = stage.value
        err_text = (
            str(original_error)
            if not isinstance(original_error, BaseException)
            else f"{type(original_error).__name__}: {original_error}"
        )
        details["original_error"] = err_text
        self.stage = stage
        self.original_error = original_error
        super().__init__(message, context=details)


class PipelineTimeoutError(PipelineError):
    """Raised when a pipeline stage exceeds its time budget.

    Args:
        message: Human-readable error description.
        stage: Stage that timed out.
        timeout_seconds: Configured timeout in seconds.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: PipelineStage,
        timeout_seconds: float,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["stage"] = stage.value
        details["timeout_seconds"] = timeout_seconds
        self.stage = stage
        self.timeout_seconds = timeout_seconds
        super().__init__(message, context=details)


class PipelineCancelledError(PipelineError):
    """Raised when a pipeline job is cancelled before completion.

    Args:
        message: Human-readable error description.
        job_id: Cancelled job identifier.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        job_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["job_id"] = job_id
        self.job_id = job_id
        super().__init__(message, context=details)


class ParserUnavailableError(PipelineError):
    """Raised when a parser cannot run because a dependency library is missing.

    Args:
        message: Human-readable error description.
        parser_name: Parser identifier.
        library_name: Missing optional library name.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        parser_name: str,
        library_name: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["parser_name"] = parser_name
        details["library_name"] = library_name
        self.parser_name = parser_name
        self.library_name = library_name
        super().__init__(message, context=details)


class AllParsersFailedError(PipelineError):
    """Raised when every applicable parser fails for an evidence type.

    Args:
        message: Human-readable error description.
        evidence_type: Evidence type that could not be parsed.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        evidence_type: EvidenceType,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["evidence_type"] = evidence_type.value
        self.evidence_type = evidence_type
        super().__init__(message, context=details)
