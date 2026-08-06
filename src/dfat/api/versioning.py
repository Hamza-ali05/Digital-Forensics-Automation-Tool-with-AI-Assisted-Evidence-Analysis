"""API versioning helpers for DFAT route registration."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter

API_V1_PREFIX = "/api/v1"


@dataclass(frozen=True)
class APIVersion:
    """Describe a published API version."""

    version: str = "1.0.0"
    prefix: str = API_V1_PREFIX
    deprecated: bool = False
    tags: list[str] = field(default_factory=lambda: ["v1"])


def create_versioned_router(version: APIVersion) -> APIRouter:
    """Create an ``APIRouter`` bound to a version prefix and tags.

    Args:
        version: API version descriptor.

    Returns:
        Configured ``APIRouter``.
    """
    tags = list(version.tags)
    if version.deprecated and "deprecated" not in tags:
        tags.append("deprecated")
    return APIRouter(prefix=version.prefix, tags=tags)
