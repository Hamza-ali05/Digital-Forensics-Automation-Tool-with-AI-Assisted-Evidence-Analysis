"""Role-based access control for forensic investigator accountability."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends

from dfat.auth.exceptions import InsufficientPermissionsError, RoleNotFoundError
from dfat.database.models.user import UserORM

ROLE_PERMISSIONS: dict[str, dict[str, list[str]]] = {
    "admin": {"all": ["create", "read", "update", "delete"]},
    "investigator": {
        "evidence": ["create", "read", "update", "delete"],
        "analysis": ["create", "read"],
        "reports": ["create", "read"],
        "evaluation": ["create", "read"],
    },
    "analyst": {
        "evidence": ["read"],
        "analysis": ["create", "read"],
        "reports": ["read"],
        "evaluation": ["read"],
    },
    "viewer": {
        "reports": ["read"],
        "evaluation": ["read"],
    },
}


class PermissionChecker:
    """Evaluate role permissions against resource/action pairs."""

    @staticmethod
    def has_permission(role: str, resource: str, action: str) -> bool:
        """Return whether ``role`` may perform ``action`` on ``resource``.

        Args:
            role: Role name (e.g. ``investigator``).
            resource: Resource name (e.g. ``evidence``).
            action: Action name (e.g. ``create``).

        Returns:
            ``True`` when permitted; otherwise ``False``.
        """
        permissions = ROLE_PERMISSIONS.get(role)
        if permissions is None:
            return False
        if "all" in permissions and action in permissions["all"]:
            return True
        allowed = permissions.get(resource, [])
        return action in allowed

    @staticmethod
    def get_permissions(role: str) -> dict[str, list[str]]:
        """Return the permission map for a role.

        Args:
            role: Role name.

        Returns:
            Resource → actions mapping.

        Raises:
            RoleNotFoundError: If the role is unknown.
        """
        permissions = ROLE_PERMISSIONS.get(role)
        if permissions is None:
            raise RoleNotFoundError(
                f"Role not found: {role}",
                context={"role": role},
            )
        return {key: list(values) for key, values in permissions.items()}

    @staticmethod
    def get_allowed_resources(role: str) -> list[str]:
        """Return resource names the role may access.

        Args:
            role: Role name.

        Returns:
            Resource names in declaration order (excluding synthetic ``all``).
        """
        permissions = PermissionChecker.get_permissions(role)
        if "all" in permissions:
            return [
                "evidence",
                "analysis",
                "reports",
                "evaluation",
                "users",
                "system",
            ]
        return [name for name in permissions if name != "all"]


def require_permission(resource: str, action: str) -> Callable[..., Awaitable[UserORM]]:
    """Build a FastAPI dependency that enforces a resource/action permission.

    Args:
        resource: Required resource name.
        action: Required action name.

    Returns:
        Async dependency callable suitable for ``Depends()``.
    """
    from dfat.auth.dependencies import get_current_active_user

    async def _dependency(
        current_user: UserORM = Depends(get_current_active_user),
    ) -> UserORM:
        role_name = _resolve_role_name(current_user)
        if not PermissionChecker.has_permission(role_name, resource, action):
            raise InsufficientPermissionsError(
                required_permission=f"{resource}:{action}",
                user_role=role_name,
            )
        return current_user

    return _dependency


def require_role(allowed_roles: list[str]) -> Callable[..., Awaitable[UserORM]]:
    """Build a FastAPI dependency that enforces membership in allowed roles.

    Args:
        allowed_roles: Role names permitted to access the endpoint.

    Returns:
        Async dependency callable suitable for ``Depends()``.
    """
    from dfat.auth.dependencies import get_current_active_user

    async def _dependency(
        current_user: UserORM = Depends(get_current_active_user),
    ) -> UserORM:
        role_name = _resolve_role_name(current_user)
        if role_name not in allowed_roles:
            raise InsufficientPermissionsError(
                required_permission=f"role in {allowed_roles}",
                user_role=role_name,
            )
        return current_user

    return _dependency


def _resolve_role_name(user: UserORM) -> str:
    """Resolve a role name from a loaded user, falling back to role_id."""
    role = getattr(user, "role", None)
    if role is not None and getattr(role, "name", None):
        return str(role.name)
    role_id = str(user.role_id)
    if role_id.startswith("role-"):
        return role_id.removeprefix("role-")
    return role_id
