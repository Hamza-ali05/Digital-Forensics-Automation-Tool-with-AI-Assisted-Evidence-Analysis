"""DFAT Authentication & Authorisation — Forensic investigator
accountability infrastructure.
"""

from dfat.auth.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    AuthenticationError,
    AuthorisationError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    RoleNotFoundError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
)
from dfat.auth.jwt_handler import JWTHandler
from dfat.auth.password import PasswordHasher, validate_password_strength
from dfat.auth.rbac import ROLE_PERMISSIONS, PermissionChecker, require_permission, require_role

__all__ = [
    "AccountDisabledError",
    "AccountLockedError",
    "AuthenticationError",
    "AuthorisationError",
    "InsufficientPermissionsError",
    "InvalidCredentialsError",
    "JWTHandler",
    "PasswordHasher",
    "PermissionChecker",
    "ROLE_PERMISSIONS",
    "RoleNotFoundError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TokenRevokedError",
    "require_permission",
    "require_role",
    "validate_password_strength",
]
