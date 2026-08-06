"""Database-layer exceptions wrapping SQLAlchemy failures."""

from __future__ import annotations

from typing import Any, Optional

from dfat.core.exceptions import DFATError


class DatabaseError(DFATError):
    """Raised when a persistence operation fails."""

    def __init__(
        self,
        message: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialise a database error.

        Args:
            message: Human-readable error description.
            context: Optional structured context.
        """
        super().__init__(message, context=context)
