"""DFAT Reporting — Dual-output JSON and narrative report generation (stage 4)."""

from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.reporting.report_builder import DualOutputReportBuilder

__all__ = [
    "DualOutputReportBuilder",
    "NarrativeAssembler",
    "StructuredJSONExporter",
]
