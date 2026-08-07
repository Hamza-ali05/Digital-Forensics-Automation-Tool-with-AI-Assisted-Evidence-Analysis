"""Case-management exceptions extending the DFAT domain error hierarchy."""

from __future__ import annotations

from typing import Any, Optional

from dfat.core.exceptions import DFATError


class CaseError(DFATError):
    """Base error for investigation case lifecycle failures."""


class CaseNotFoundError(CaseError):
    """Raised when a case identifier cannot be resolved.

    Args:
        message: Human-readable error description.
        case_id: Missing case identifier.
        context: Optional structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        case_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        details = dict(context or {})
        details["case_id"] = case_id
        self.case_id = case_id
        super().__init__(message, context=details)


class InvalidCaseTransitionError(CaseError):
    """Raised when a case status transition is not permitted.

    Args:
        message: Human-readable error description.
        current_status: Current case status value.
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


class CaseAlreadyClosedError(CaseError):
    """Raised when an operation requires an open case that is already closed."""


class InvestigatorAlreadyAssignedError(CaseError):
    """Raised when assigning an investigator who is already on the case."""


class NoLeadInvestigatorError(CaseError):
    """Raised when a case operation requires a lead investigator and none is set."""
