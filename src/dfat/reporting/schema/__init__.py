"""DFAT report JSON Schema package — draft-07 validation and versioning."""

from dfat.reporting.schema.schema_validator import (
    ReportSchemaValidator,
    ValidationResult,
)
from dfat.reporting.schema.schema_versions import (
    SCHEMA_REGISTRY,
    get_latest_version,
    get_schema,
    get_schema_path,
)

__all__ = [
    "SCHEMA_REGISTRY",
    "ReportSchemaValidator",
    "ValidationResult",
    "get_latest_version",
    "get_schema",
    "get_schema_path",
]

