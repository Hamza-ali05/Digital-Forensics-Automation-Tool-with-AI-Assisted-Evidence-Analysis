"""Validate forensic JSON report documents against the draft-07 schema."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import jsonschema
from pydantic import BaseModel, ConfigDict, Field

from dfat.reporting.schema.schema_versions import (
    get_latest_version,
    get_schema_path,
)


class ValidationResult(BaseModel):
    """Outcome of validating a report document against the JSON Schema."""

    model_config = ConfigDict(frozen=False)

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    schema_version: str
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReportSchemaValidator:
    """Enforce the DFAT forensic report JSON Schema (draft-07)."""

    def __init__(self, schema_path: Optional[Path] = None) -> None:
        """Initialise the validator.

        Args:
            schema_path: Optional path to a schema file. Defaults to the latest
                registered schema version (``1.0.0``).
        """
        self._schema_path = schema_path or get_schema_path()
        with self._schema_path.open("r", encoding="utf-8") as handle:
            import json

            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError(f"Schema at {self._schema_path} is not a JSON object")
        self._schema: dict[str, Any] = loaded
        self._schema_version = str(
            self._schema.get("version")
            or self._schema.get("const")
            or get_latest_version()
        )
        # Prefer explicit schema_version const when present.
        props = self._schema.get("properties") or {}
        version_prop = props.get("schema_version") if isinstance(props, dict) else None
        if isinstance(version_prop, dict) and "const" in version_prop:
            self._schema_version = str(version_prop["const"])
        self._validator = jsonschema.Draft7Validator(
            self._schema,
            format_checker=jsonschema.FormatChecker(),
        )

    def validate(self, report_data: dict[str, Any]) -> ValidationResult:
        """Validate ``report_data`` against the loaded schema.

        Args:
            report_data: Candidate forensic report document.

        Returns:
            ``ValidationResult`` with errors/warnings (never raises).
        """
        errors = sorted(
            self._validator.iter_errors(report_data),
            key=lambda err: list(err.path),
        )
        messages = [
            f"{'/'.join(str(part) for part in err.path) or '<root>'}: {err.message}"
            for err in errors
        ]
        warnings: list[str] = []
        if (
            isinstance(report_data, dict)
            and "reproducibility" not in report_data
            and self._schema_version == "1.0.0"
        ):
            warnings.append(
                "Optional field 'reproducibility' is absent; "
                "integrity still covers artefact_data only."
            )
        return ValidationResult(
            is_valid=not messages,
            errors=messages,
            warnings=warnings,
            schema_version=self._schema_version,
        )

    def get_schema_version(self) -> str:
        """Return the schema version this validator enforces."""
        return self._schema_version

    def get_required_fields(self) -> list[str]:
        """Return top-level required field names from the schema."""
        required = self._schema.get("required", [])
        if not isinstance(required, list):
            return []
        return [str(item) for item in required]

    @property
    def schema(self) -> dict[str, Any]:
        """Return the loaded schema document."""
        return self._schema

    @property
    def schema_path(self) -> Path:
        """Return the path of the loaded schema file."""
        return self._schema_path

    @classmethod
    def from_version(cls, version: str) -> ReportSchemaValidator:
        """Build a validator for a registered schema version."""
        return cls(schema_path=get_schema_path(version))

