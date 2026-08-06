"""Authentication and authorisation exceptions for DFAT.

These extend ``DFATError`` without modifying ``src/dfat/core/exceptions.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from dfat.core.exceptions import DFATError


class AuthenticationError(DFATError):
    """Base error for authentication failures."""


class InvalidCredentialsError(AuthenticationError):
    """Raised when username/password authentication fails."""

    def __init__(
        self,
        message: str = "Invalid username or password",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialise with a generic credentials failure message.

        Args:
            message: Human-readable error description.
            context: Optional structured context (avoid leaking specifics).
        """
        super().__init__(message, context=context)


class TokenExpiredError(AuthenticationError):
    """Raised when a JWT has passed its expiry time."""

    def __init__(
        self,
        message: str = "Token has expired",
        *,
        token_type: str = "access",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialise a token-expiry error.

        Args:
            message: Human-readable error description.
            token_type: ``access`` or ``refresh``.
            context: Optional structured context.
        """
        details = dict(context or {})
        details["token_type"] = token_type
        self.token_type = token_type
        super().__init__(message, context=details)


class TokenInvalidError(AuthenticationError):
    """Raised when a JWT is malformed or fails signature validation."""


class TokenRevokedError(AuthenticationError):
    """Raised when a JWT has been revoked."""


class AccountLockedError(AuthenticationError):
    """Raised when an account is temporarily locked after failed logins."""

    def __init__(
        self,
        message: str = "Account is locked",
        *,
        locked_until: Optional[datetime] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialise an account-lock error.

        Args:
            message: Human-readable error description.
            locked_until: Optional lock expiry timestamp.
            context: Optional structured context.
        """
        details = dict(context or {})
        if locked_until is not None:
            details["locked_until"] = locked_until.isoformat()
        self.locked_until = locked_until
        super().__init__(message, context=details)


class AccountDisabledError(AuthenticationError):
    """Raised when an account has been disabled by an administrator."""


class AuthorisationError(DFATError):
    """Base error for authorisation / RBAC failures."""


class InsufficientPermissionsError(AuthorisationError):
    """Raised when the caller's role lacks a required permission."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        *,
        required_permission: str,
        user_role: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialise a permissions failure.

        Args:
            message: Human-readable error description.
            required_permission: Permission that was required.
            user_role: Caller's role name.
            context: Optional structured context.
        """
        details = dict(context or {})
        details["required_permission"] = required_permission
        details["user_role"] = user_role
        self.required_permission = required_permission
        self.user_role = user_role
        super().__init__(message, context=details)


class RoleNotFoundError(AuthorisationError):
    """Raised when a requested role cannot be resolved."""
