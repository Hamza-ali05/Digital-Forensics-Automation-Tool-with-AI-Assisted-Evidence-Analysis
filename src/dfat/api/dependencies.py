"""FastAPI dependency providers extracting services from the DI container."""

from __future__ import annotations

from fastapi import Request

from dfat.auth.dependencies import (
    get_current_active_user,
    get_current_user,
    get_jwt_handler,
    get_optional_user,
    get_session_repo,
    get_user_repo,
    oauth2_scheme,
)
from dfat.auth.rbac import PermissionChecker, require_permission, require_role
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
from dfat.pipeline import PipelineOrchestrator
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.services.analysis_service import AnalysisService
from dfat.services.audit_service import AuditService
from dfat.services.evaluation_service import EvaluationService
from dfat.services.evidence_service import EvidenceService
from dfat.services.report_service import ReportService
from dfat.services.user_service import UserService


def _container(request: Request):  # type: ignore[no-untyped-def]
    """Return the application DI container from request state."""
    return request.app.state.container


def get_forensic_orchestrator(request: Request) -> PipelineOrchestrator:
    """Provide the top-level pipeline orchestrator."""
    return _container(request).pipeline.pipeline_orchestrator()


def get_report_builder(request: Request) -> DualOutputReportBuilder:
    """Provide the dual-output report builder."""
    return _container(request).reporting_engine.report_builder()


def get_benchmark_comparator(request: Request) -> BenchmarkComparator:
    """Provide the benchmark comparator."""
    return _container(request).evaluation_engine.comparator()


def get_evidence_repository(request: Request) -> FileSystemEvidenceRepository:
    """Provide the file-based evidence repository (sync pipeline fallback)."""
    return _container(request).repositories.file_evidence_repo()


def get_report_repository(request: Request) -> FileSystemReportRepository:
    """Provide the file-based report repository (sync pipeline fallback)."""
    return _container(request).repositories.file_report_repo()


def get_audit_logger(request: Request) -> ForensicAuditLogger:
    """Provide the forensic audit logger."""
    return _container(request).logging.forensic_audit_logger()


def get_disk_image_handler(request: Request) -> DiskImageHandler:
    """Provide the disk image acquisition handler."""
    return _container(request).forensic_engine.image_handler()


def get_memory_dump_handler(request: Request) -> MemoryDumpHandler:
    """Provide the memory dump acquisition handler."""
    return _container(request).forensic_engine.memory_handler()


def get_user_service(request: Request) -> UserService:
    """Resolve the user authentication/account service."""
    return _container(request).services.user_service()


def get_audit_service(request: Request) -> AuditService:
    """Resolve the dual-write audit service."""
    return _container(request).services.audit_service()


def get_evidence_service(request: Request) -> EvidenceService:
    """Resolve the evidence registration service."""
    return _container(request).services.evidence_service()


def get_analysis_service(request: Request) -> AnalysisService:
    """Resolve the analysis pipeline service."""
    return _container(request).services.analysis_service()


def get_report_service(request: Request) -> ReportService:
    """Resolve the report retrieval service."""
    return _container(request).services.report_service()


def get_evaluation_service(request: Request) -> EvaluationService:
    """Resolve the evaluation/benchmark service."""
    return _container(request).services.evaluation_service()


__all__ = [
    "PermissionChecker",
    "get_analysis_service",
    "get_audit_logger",
    "get_audit_service",
    "get_benchmark_comparator",
    "get_current_active_user",
    "get_current_user",
    "get_disk_image_handler",
    "get_evaluation_service",
    "get_evidence_repository",
    "get_evidence_service",
    "get_forensic_orchestrator",
    "get_jwt_handler",
    "get_memory_dump_handler",
    "get_optional_user",
    "get_report_builder",
    "get_report_repository",
    "get_report_service",
    "get_session_repo",
    "get_user_repo",
    "get_user_service",
    "oauth2_scheme",
    "require_permission",
    "require_role",
]
