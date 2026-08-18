"""Shared Pydantic configuration for DFAT API serialization."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

API_JSON_ENCODERS: dict[type[Any], Any] = {
    datetime: lambda value: value.isoformat(),
    Path: str,
    UUID: str,
}

API_MODEL_CONFIG = ConfigDict(json_encoders=API_JSON_ENCODERS)


class APIModel(BaseModel):
    """Base model for API responses with stable JSON encoding.

    Datetimes serialize to ISO-8601, filesystem paths and UUIDs to strings.
    Callers that need a JSON-compatible dict should use
    ``model_dump(mode="json")``.
    """

    model_config = API_MODEL_CONFIG
