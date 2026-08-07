"""Unit tests for RBAC permission matrix."""

from __future__ import annotations

import pytest

from dfat.auth.rbac import PermissionChecker


def test_admin_has_all_permissions() -> None:
    """Admin role can perform any action on any resource."""
    # Arrange / Act / Assert
    assert PermissionChecker.has_permission("admin", "evidence", "create") is True
    assert PermissionChecker.has_permission("admin", "users", "delete") is True
    assert PermissionChecker.has_permission("admin", "system", "update") is True


def test_viewer_cannot_create_evidence() -> None:
    """Viewer role cannot create evidence."""
    # Arrange / Act / Assert
    assert PermissionChecker.has_permission("viewer", "evidence", "create") is False
    assert PermissionChecker.has_permission("viewer", "evidence", "read") is False


def test_analyst_can_create_analysis() -> None:
    """Analyst role can create analysis runs."""
    # Arrange / Act / Assert
    assert PermissionChecker.has_permission("analyst", "analysis", "create") is True
    assert PermissionChecker.has_permission("analyst", "evidence", "read") is True


def test_investigator_can_create_evidence() -> None:
    """Investigator role can create evidence."""
    # Arrange / Act / Assert
    assert PermissionChecker.has_permission("investigator", "evidence", "create") is True
    assert PermissionChecker.has_permission("investigator", "evaluation", "create") is True


def test_unknown_role_has_no_permissions() -> None:
    """Unknown roles are denied all permissions."""
    # Arrange / Act / Assert
    assert PermissionChecker.has_permission("ghost", "evidence", "read") is False
    assert PermissionChecker.has_permission("ghost", "reports", "read") is False


def test_get_permissions_and_allowed_resources() -> None:
    """Permission maps and allowed resource lists are exposed for known roles."""
    # Arrange / Act
    admin_perms = PermissionChecker.get_permissions("admin")
    viewer_resources = PermissionChecker.get_allowed_resources("viewer")
    analyst_resources = PermissionChecker.get_allowed_resources("analyst")

    # Assert
    assert "all" in admin_perms
    assert "reports" in viewer_resources
    assert "evidence" in analyst_resources
    assert PermissionChecker.get_allowed_resources("admin") == [
        "evidence",
        "analysis",
        "reports",
        "evaluation",
        "cases",
        "users",
        "system",
    ]


def test_get_permissions_unknown_role_raises() -> None:
    """Unknown roles raise RoleNotFoundError from get_permissions."""
    from dfat.auth.exceptions import RoleNotFoundError

    with pytest.raises(RoleNotFoundError):
        PermissionChecker.get_permissions("ghost")
