"""DFAT Application Services — Business logic layer."""

from __future__ import annotations

from typing import Any

from dfat.services.audit_service import AuditService
from dfat.services.evaluation_service import EvaluationService
from dfat.services.evidence_service import EvidenceService
from dfat.services.report_service import ReportService
from dfat.services.user_service import UserService

# AnalysisService imports PipelineOrchestrator; keep it lazy so
# ``from dfat.services.audit_service import AuditService`` (used by custody /
# pipeline) does not create a circular import via this package __init__.

__all__ = [
    "AnalysisService",
    "AuditService",
    "EvaluationService",
    "EvidenceService",
    "ReportService",
    "UserService",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve symbols that would otherwise create import cycles."""
    if name == "AnalysisService":
        from dfat.services.analysis_service import AnalysisService

        return AnalysisService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
