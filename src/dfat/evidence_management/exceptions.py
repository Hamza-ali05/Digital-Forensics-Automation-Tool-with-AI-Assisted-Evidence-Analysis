"""Evidence-management exceptions extending the DFAT domain error hierarchy."""

from __future__ import annotations

from typing import Any, Optional

from dfat.core.exceptions import DFATError


class EvidenceManagementError(DFATError):
    """Base error for evidence validation, custody, and metadata failures."""


class InvalidEvidenceTransitionError(EvidenceManagementError):
    """Raised when an evidence status transition is not permitted.

    Args:
        message: Human-readable error description.
        current_status: Current evidence status value.
        attempted_status: Requested next status value.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        current_status: str,
        attempted_status: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["current_status"] = current_status
        details["attempted_status"] = attempted_status
        self.current_status = current_status
        self.attempted_status = attempted_status
        super().__init__(message, context=details)


class EvidenceValidationError(EvidenceManagementError):
    """Raised when evidence fails format, size, or integrity validation.

    Args:
        message: Human-readable error description.
        validation_failures: List of validation failure messages.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        validation_failures: list[str],
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["validation_failures"] = list(validation_failures)
        self.validation_failures = list(validation_failures)
        super().__init__(message, context=details)


class MIMETypeMismatchError(EvidenceManagementError):
    """Raised when declared MIME type does not match detected type.

    Args:
        message: Human-readable error description.
        expected_mime: Expected MIME type.
        detected_mime: Detected MIME type.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        expected_mime: str,
        detected_mime: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["expected_mime"] = expected_mime
        details["detected_mime"] = detected_mime
        self.expected_mime = expected_mime
        self.detected_mime = detected_mime
        super().__init__(message, context=details)


class CustodyChainError(EvidenceManagementError):
    """Base error for chain-of-custody failures."""


class CustodyRecordNotFoundError(CustodyChainError):
    """Raised when a custody record cannot be located."""


class EvidenceQuarantinedError(EvidenceManagementError):
    """Raised when an operation is blocked because evidence is quarantined.

    Args:
        message: Human-readable error description.
        evidence_id: Quarantined evidence identifier.
        reason: Quarantine reason.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        evidence_id: str,
        reason: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["evidence_id"] = evidence_id
        details["reason"] = reason
        self.evidence_id = evidence_id
        self.reason = reason
        super().__init__(message, context=details)
