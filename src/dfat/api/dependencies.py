"""FastAPI dependency providers extracting services from the DI container."""

from __future__ import annotations

from fastapi import Request

from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
from dfat.pipeline import PipelineOrchestrator
from dfat.reporting.report_builder import DualOutputReportBuilder


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
    """Provide the evidence repository."""
    return _container(request).repositories.evidence_repo()


def get_report_repository(request: Request) -> FileSystemReportRepository:
    """Provide the report repository."""
    return _container(request).repositories.report_repo()


def get_audit_logger(request: Request) -> ForensicAuditLogger:
    """Provide the forensic audit logger."""
    return _container(request).logging.forensic_audit_logger()


def get_disk_image_handler(request: Request) -> DiskImageHandler:
    """Provide the disk image acquisition handler."""
    return _container(request).forensic_engine.image_handler()


def get_memory_dump_handler(request: Request) -> MemoryDumpHandler:
    """Provide the memory dump acquisition handler."""
    return _container(request).forensic_engine.memory_handler()
