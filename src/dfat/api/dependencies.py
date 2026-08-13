"""FastAPI dependency providers extracting services from the DI container."""

from __future__ import annotations

from fastapi import Request

from dfat.ai_engine.analyzer import LocalLLMClient
from dfat.ai_engine.assistance.investigator_qa import InvestigatorQAAssistant
from dfat.ai_engine.caching.response_cache import AIResponseCache
from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.ai_engine.monitoring.ai_monitor import AIMonitor
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
from dfat.database.repositories.ai_analysis_repo import SQLAlchemyAIAnalysisRepository
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
from dfat.pipeline import PipelineOrchestrator
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.services.analysis_service import AnalysisService
from dfat.services.audit_service import AuditService
from dfat.services.case_service import CaseService
from dfat.services.evaluation_service import EvaluationService
from dfat.services.evidence_management_service import EvidenceManagementService
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


def get_response_collector(request: Request):
    """Resolve the anonymised usability response collector."""
    return _container(request).evaluation_engine.response_collector()


def get_performance_analyzer(request: Request):
    """Resolve the benchmark performance analyzer."""
    return _container(request).evaluation_engine.performance_analyzer()


def get_integrity_verifier(request: Request):
    """Resolve the report integrity verifier."""
    return _container(request).reporting_engine.integrity_verifier()


def get_reproducibility_verifier(request: Request):
    """Resolve the report reproducibility verifier."""
    return _container(request).reporting_engine.reproducibility_verifier()


def get_case_service(request: Request) -> CaseService:
    """Resolve the case lifecycle management service."""
    return _container(request).services.case_service()


def get_evidence_management_service(request: Request) -> EvidenceManagementService:
    """Resolve the enhanced evidence management service."""
    return _container(request).services.evidence_management_service()


def get_custody_service(request: Request) -> ChainOfCustodyService:
    """Resolve the chain-of-custody service."""
    return _container(request).services.chain_of_custody_service()


def get_llm_client(request: Request) -> LocalLLMClient:
    """Provide the assembled local LLaMA-3 analyser client."""
    return _container(request).ai_engine.llm_client()


def get_qa_assistant(request: Request) -> InvestigatorQAAssistant:
    """Provide the investigator Q&A assistant (via the LLM client)."""
    return get_llm_client(request).get_qa_assistant()


def get_fallback_analyzer(request: Request) -> RuleBasedAnalyzer:
    """Provide the rule-based AI fallback analyser."""
    return _container(request).ai_engine.fallback()


def get_llm_connection_manager(request: Request) -> LLMConnectionManager:
    """Provide the Ollama connection/health manager."""
    return _container(request).ai_engine.connection_manager()


def get_ai_monitor(request: Request) -> AIMonitor:
    """Provide the AI usage monitor."""
    return _container(request).ai_engine.ai_monitor()


def get_ai_response_cache(request: Request) -> AIResponseCache:
    """Provide the AI response cache."""
    return _container(request).ai_engine.ai_response_cache()


def get_artefact_repository(request: Request) -> SQLAlchemyArtefactRepository:
    """Provide the SQLAlchemy artefact repository."""
    return _container(request).repositories.artefact_repo()


def get_ai_analysis_repo(request: Request) -> SQLAlchemyAIAnalysisRepository:
    """Provide the AI analysis record repository."""
    return _container(request).repositories.ai_analysis_repo()


__all__ = [
    "PermissionChecker",
    "get_ai_analysis_repo",
    "get_ai_monitor",
    "get_ai_response_cache",
    "get_analysis_service",
    "get_artefact_repository",
    "get_audit_logger",
    "get_audit_service",
    "get_benchmark_comparator",
    "get_case_service",
    "get_current_active_user",
    "get_current_user",
    "get_custody_service",
    "get_disk_image_handler",
    "get_evaluation_service",
    "get_evidence_management_service",
    "get_evidence_repository",
    "get_evidence_service",
    "get_fallback_analyzer",
    "get_forensic_orchestrator",
    "get_integrity_verifier",
    "get_jwt_handler",
    "get_llm_client",
    "get_llm_connection_manager",
    "get_memory_dump_handler",
    "get_optional_user",
    "get_performance_analyzer",
    "get_qa_assistant",
    "get_report_builder",
    "get_report_repository",
    "get_report_service",
    "get_reproducibility_verifier",
    "get_response_collector",
    "get_session_repo",
    "get_user_repo",
    "get_user_service",
    "oauth2_scheme",
    "require_permission",
    "require_role",
]
