"""DFAT Reporting — Dual-output JSON and narrative report generation (stage 4)."""

from dfat.reporting.exporters import (
    HTMLReportExporter,
    JSONFileExporter,
    PDFReportExporter,
)
from dfat.reporting.generators import (
    AuditReportGenerator,
    AuditTrailReport,
    CustodyReport,
    CustodyReportGenerator,
)
from dfat.reporting.integrity import (
    IntegrityVerificationResult,
    ReportIntegrityVerifier,
)
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.reporting.reproducibility import (
    ReproducibilityResult,
    ReproducibilityVerifier,
)
from dfat.reporting.schema import (
    SCHEMA_REGISTRY,
    ReportSchemaValidator,
    ValidationResult,
    get_latest_version,
    get_schema,
)

__all__ = [
    "SCHEMA_REGISTRY",
    "AuditReportGenerator",
    "AuditTrailReport",
    "CustodyReport",
    "CustodyReportGenerator",
    "DualOutputReportBuilder",
    "HTMLReportExporter",
    "IntegrityVerificationResult",
    "JSONFileExporter",
    "NarrativeAssembler",
    "PDFReportExporter",
    "ReportIntegrityVerifier",
    "ReportSchemaValidator",
    "ReproducibilityResult",
    "ReproducibilityVerifier",
    "StructuredJSONExporter",
    "ValidationResult",
    "get_latest_version",
    "get_schema",
]

