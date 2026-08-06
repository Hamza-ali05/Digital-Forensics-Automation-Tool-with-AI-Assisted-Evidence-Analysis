"""DFAT domain-specific exception hierarchy."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory


class DFATError(Exception):
    """Base exception for all DFAT domain errors.

    Args:
        message: Human-readable error description.
        context: Structured context for audit trail integration.
    """

    def __init__(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.context: dict[str, Any] = context if context is not None else {}
        self.timestamp: datetime = datetime.now(UTC)
        super().__init__(message)

    def __str__(self) -> str:
        """Return formatted exception string with context."""
        return f"[{self.__class__.__name__}] {self.message} (context: {self.context})"


class EvidenceError(DFATError):
    """Base error for evidence acquisition and integrity failures."""


class EvidenceNotFoundError(EvidenceError):
    """Raised when an evidence file path does not exist or is inaccessible."""


class IntegrityVerificationError(EvidenceError):
    """Raised when an evidence integrity hash does not match expectations.

    Args:
        message: Human-readable error description.
        expected_hash: Hash value that was expected.
        actual_hash: Hash value that was computed.
        context: Additional structured context.
    """

    def __init__(
        self,
        message: str,
        expected_hash: str,
        actual_hash: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        merged = dict(context) if context is not None else {}
        merged.update(
            {
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            }
        )
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(message, context=merged)


class UnsupportedFormatError(EvidenceError):
    """Raised when evidence format/extension is not supported."""


class ParsingError(DFATError):
    """Base error for artefact parsing failures."""


class DiskParsingError(ParsingError):
    """Raised when disk image parsing fails."""


class MemoryParsingError(ParsingError):
    """Raised when memory dump parsing fails."""


class ArtefactExtractionError(ParsingError):
    """Raised when a specific artefact category cannot be extracted.

    Args:
        message: Human-readable error description.
        artefact_category: Category that failed extraction.
        context: Additional structured context.
    """

    def __init__(
        self,
        message: str,
        artefact_category: ArtefactCategory,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        merged = dict(context) if context is not None else {}
        merged["artefact_category"] = (
            artefact_category.value
            if isinstance(artefact_category, ArtefactCategory)
            else artefact_category
        )
        self.artefact_category = artefact_category
        super().__init__(message, context=merged)


class AIEngineError(DFATError):
    """Base error for local AI triage engine failures."""


class LLMConnectionError(AIEngineError):
    """Raised when the local LLM API cannot be reached."""


class LLMTimeoutError(AIEngineError):
    """Raised when the local LLM API call exceeds the timeout."""


class LLMResponseError(AIEngineError):
    """Raised when the local LLM returns an invalid or unusable response."""


class ReportingError(DFATError):
    """Base error for report generation failures."""


class TemplateError(ReportingError):
    """Raised when a narrative or report template cannot be rendered."""


class JSONSchemaValidationError(ReportingError):
    """Raised when structured JSON report fails schema validation.

    Args:
        message: Human-readable error description.
        validation_errors: List of schema validation error details.
        context: Additional structured context.
    """

    def __init__(
        self,
        message: str,
        validation_errors: list[str],
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        merged = dict(context) if context is not None else {}
        merged["validation_errors"] = validation_errors
        self.validation_errors = validation_errors
        super().__init__(message, context=merged)


class EvaluationError(DFATError):
    """Base error for benchmark and usability evaluation failures."""


class GroundTruthNotFoundError(EvaluationError):
    """Raised when a ground-truth dataset file cannot be located."""


class MetricsCalculationError(EvaluationError):
    """Raised when precision/recall/F1 or related metrics cannot be computed."""
