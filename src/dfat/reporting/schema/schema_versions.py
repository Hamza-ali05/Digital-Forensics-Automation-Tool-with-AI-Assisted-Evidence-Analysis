"""Schema version registry for DFAT forensic JSON reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMA_DIR = Path(__file__).resolve().parent

SCHEMA_REGISTRY: dict[str, Path] = {
    "1.0.0": _SCHEMA_DIR / "report_schema.json",
}

_LATEST_VERSION = "1.0.0"


def get_latest_version() -> str:
    """Return the latest supported report schema version."""
    return _LATEST_VERSION


def get_schema(version: str | None = None) -> dict[str, Any]:
    """Load and return a report schema document by version.

    Args:
        version: Schema version string. Defaults to the latest version.

    Returns:
        Parsed JSON Schema object.

    Raises:
        KeyError: If ``version`` is not registered.
        FileNotFoundError: If the schema file is missing.
        json.JSONDecodeError: If the schema file is not valid JSON.
    """
    resolved = version or get_latest_version()
    path = SCHEMA_REGISTRY.get(resolved)
    if path is None:
        raise KeyError(f"Unknown report schema version: {resolved}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Schema at {path} is not a JSON object")
    return data


def get_schema_path(version: str | None = None) -> Path:
    """Return the filesystem path for a registered schema version."""
    resolved = version or get_latest_version()
    path = SCHEMA_REGISTRY.get(resolved)
    if path is None:
        raise KeyError(f"Unknown report schema version: {resolved}")
    return path

