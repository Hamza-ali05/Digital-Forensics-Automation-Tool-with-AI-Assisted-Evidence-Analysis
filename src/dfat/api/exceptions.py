"""API-layer exceptions (HTTP-facing, not domain core)."""

from __future__ import annotations

from typing import Any, Optional

from dfat.core.exceptions import DFATError


class RateLimitExceededError(DFATError):
    """Raised when a client exceeds a configured rate limit."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after_seconds: int = 60,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialise a rate-limit error.

        Args:
            message: Human-readable error description.
            retry_after_seconds: Suggested retry delay for clients.
            context: Optional structured context.
        """
        details = dict(context or {})
        details["retry_after_seconds"] = retry_after_seconds
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message, context=details)
