"""Dependency injection container for DFAT application wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dependency_injector import containers, providers

from dfat.ai_engine.analyzer import LocalLLMClient
from dfat.ai_engine.caching.response_cache import AIResponseCache
from dfat.ai_engine.classification.classifier import (
    DefaultConfidenceScorer as ClassificationDefaultConfidenceScorer,
    LLMArtefactClassifier,
)
from dfat.ai_engine.classification.parser import ClassificationResponseParser
from dfat.ai_engine.classification.prompts import ClassificationPromptBuilder
from dfat.ai_engine.explanation.confidence import ConfidenceScorer
from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.client import OllamaClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.monitoring.ai_monitor import AIMonitor
from dfat.ai_engine.preprocessing.batcher import ArtefactBatcher
from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.ai_engine.ranking.parser import RankingResponseParser
from dfat.ai_engine.ranking.prompts import RankingPromptBuilder
from dfat.ai_engine.ranking.ranker import LLMRelevanceRanker
from dfat.ai_engine.selector import select_analyzer
from dfat.ai_engine.summarization.prompts import SummarizationPromptBuilder
from dfat.ai_engine.summarization.summarizer import LLMInvestigativeSummarizer
from dfat.ai_engine.summarization.validator import SummaryResponseValidator
from dfat.ai_engine.triage.classifier import ArtefactClassifier
from dfat.ai_engine.triage.ranker import RelevanceRanker
from dfat.ai_engine.triage.summarizer import InvestigativeSummarizer
from dfat.ai_engine.validation.response_validator import AIResponseValidator
from dfat.core.enums import HashAlgorithm
from dfat.core.interfaces.parser import IArtefactParser
from dfat.core.interfaces.reporter import IReportGenerator
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.forensic_engine.normalizer import ArtefactNormalizer
from dfat.forensic_engine.orchestrator import ForensicOrchestrator
from dfat.forensic_engine.parsers.browser import BrowserHistoryParser
from dfat.forensic_engine.parsers.disk_access import DiskImageAccessor
from dfat.forensic_engine.parsers.eventlog import EventLogParser
from dfat.forensic_engine.parsers.filesystem import FileSystemParser
from dfat.forensic_engine.parsers.memory.injection import CodeInjectionParser
from dfat.forensic_engine.parsers.memory.network import NetworkArtefactParser
from dfat.forensic_engine.parsers.memory.process import ProcessListParser
from dfat.forensic_engine.parsers.memory.plugin_executor import PluginExecutor
from dfat.forensic_engine.parsers.memory.registry_mem import MemoryRegistryParser
from dfat.forensic_engine.parsers.memory.volatility_runner import VolatilityRunner
from dfat.forensic_engine.parsers.registry import RegistryParser
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.metadata_service import EvidenceMetadataService
from dfat.evidence_management.mime_identifier import MIMEIdentifier
from dfat.evidence_management.validation_service import EvidenceValidationService
from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.dfrws_handler import DFRWSHandler
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.evaluation.benchmark.performance import PerformanceAnalyzer
from dfat.evaluation.benchmark.visualisation import MetricsVisualiser
from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument
from dfat.evaluation.usability.response_analyzer import ResponseAnalyzer
from dfat.evaluation.usability.response_collector import ResponseCollector
from dfat.infrastructure.cache.artefact_cache import InMemoryArtefactCache
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger, setup_logging
from dfat.infrastructure.repositories.artefact_repo import JSONArtefactRepository
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
from dfat.infrastructure.storage.local_storage import LocalFileStorage
from dfat.infrastructure.storage.secure_storage import SecureStorage
from dfat.pipeline import PipelineOrchestrator
from dfat.pipeline.job_manager import JobManager
from dfat.pipeline.job_runner import JobRunner
from dfat.pipeline.error_handler import PipelineErrorHandler
from dfat.pipeline.evidence_discovery import EvidenceDiscoveryService
from dfat.pipeline.evidence_loader import EvidenceLoader
from dfat.pipeline.evidence_router import EvidenceRouter
from dfat.pipeline.parser_registry import ParserRegistry
from dfat.pipeline.pipeline_logger import PipelineLogger
from dfat.pipeline.progress_tracker import ProgressTracker
from dfat.pipeline.stage_registry import StageRegistry
from dfat.pipeline.stages.acquisition_stage import AcquisitionStage
from dfat.pipeline.stages.evaluation_stage import EvaluationStage
from dfat.pipeline.stages.parsing_stage import ParsingStage
from dfat.pipeline.stages.reporting_stage import ReportingStage
from dfat.pipeline.stages.triage_stage import TriageStage
from dfat.forensic_engine.processing.categoriser import ArtefactCategoriser
from dfat.forensic_engine.processing.correlator import ArtefactCorrelator
from dfat.forensic_engine.processing.deduplicator import ArtefactDeduplicator
from dfat.forensic_engine.processing.ioc_detector import IOCDetector
from dfat.forensic_engine.processing.relationship_mapper import RelationshipMapper
from dfat.forensic_engine.processing.standardiser import ArtefactStandardiser
from dfat.forensic_engine.processing.timeline import TimelineGenerator
from dfat.forensic_engine.triage.aggregator import TriageAggregator
from dfat.forensic_engine.triage.rule_engine import RuleBasedTriageEngine
from dfat.forensic_engine.triage.scoring import ScoringEngine
from dfat.reporting.exporters.html_exporter import HTMLReportExporter
from dfat.reporting.exporters.json_file_exporter import JSONFileExporter
from dfat.reporting.exporters.pdf_exporter import PDFReportExporter
from dfat.reporting.generators.audit_report import AuditReportGenerator
from dfat.reporting.generators.custody_report import CustodyReportGenerator
from dfat.reporting.integrity import ReportIntegrityVerifier
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.reporting.reproducibility import ReproducibilityVerifier
from dfat.reporting.schema import ReportSchemaValidator
from dfat.reporting.schema.schema_versions import get_schema_path as _canonical_schema_path
from dfat.auth.jwt_handler import JWTHandler
from dfat.auth.password import PasswordHasher
from dfat.auth.rbac import PermissionChecker
from dfat.database.engine import DatabaseEngine
from dfat.database.repositories.ai_analysis_repo import SQLAlchemyAIAnalysisRepository
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.custody_repo import CustodyRepository
from dfat.database.repositories.evaluation_repo import (
    SQLAlchemyBenchmarkRepository,
    SQLAlchemyUsabilityRepository,
)
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.evidence_status_repo import (
    EvidenceMetadataRepository,
    EvidenceStatusRepository,
)
from dfat.database.repositories.pipeline_repo import SQLAlchemyPipelineRepository
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository
from dfat.database.repositories.session_repo import SessionRepository
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository
from dfat.services.analysis_service import AnalysisService
from dfat.services.audit_service import AuditService
from dfat.services.case_service import CaseService
from dfat.services.evaluation_service import EvaluationService
from dfat.services.evidence_management_service import EvidenceManagementService
from dfat.services.evidence_service import EvidenceService
from dfat.services.report_service import ReportService
from dfat.services.user_service import UserService
from dfat.settings import (
    AIEngineSettings,
    AuthSettings,
    DFATSettings,
    EvidenceSettings,
    LoggingSettings,
    PipelineSettings,
    load_settings,
)


def _audit_log_path(settings: DFATSettings) -> Path:
    """Extract audit log path from settings."""
    return settings.logging.audit_log_path


def _primary_hash(settings: DFATSettings) -> HashAlgorithm:
    """Extract primary hash algorithm from settings."""
    return settings.security.primary_hash


def _evidence_dir(settings: DFATSettings) -> Path:
    """Extract evidence directory from settings."""
    return settings.evidence.evidence_dir


def _output_dir(settings: DFATSettings) -> Path:
    """Extract reporting output directory from settings."""
    return settings.reporting.output_dir


def _logging_settings(settings: DFATSettings) -> LoggingSettings:
    """Extract nested logging settings."""
    return settings.logging


def _database_url(settings: DFATSettings) -> str:
    """Extract database URL from settings."""
    return settings.database.url


def _database_echo(settings: DFATSettings) -> bool:
    """Extract database SQL echo flag from settings."""
    return settings.database.echo


def _database_pool_size(settings: DFATSettings) -> int:
    """Extract database pool size from settings."""
    return settings.database.pool_size


def _database_max_overflow(settings: DFATSettings) -> int:
    """Extract database max overflow from settings."""
    return settings.database.max_overflow


def _auth_secret_key(settings: DFATSettings) -> str:
    """Extract JWT secret key from settings."""
    return settings.auth.secret_key


def _auth_algorithm(settings: DFATSettings) -> str:
    """Extract JWT algorithm from settings."""
    return settings.auth.algorithm


def _auth_access_expire(settings: DFATSettings) -> int:
    """Extract access-token expiry minutes from settings."""
    return settings.auth.access_token_expire_minutes


def _auth_settings(settings: DFATSettings) -> AuthSettings:
    """Extract nested authentication settings."""
    return settings.auth


def _auth_refresh_expire(settings: DFATSettings) -> int:
    """Extract refresh-token expiry days from settings."""
    return settings.auth.refresh_token_expire_days


def _pipeline_settings(settings: DFATSettings) -> PipelineSettings:
    """Extract nested pipeline orchestration settings."""
    return settings.pipeline


def _evidence_settings(settings: DFATSettings) -> EvidenceSettings:
    """Extract nested evidence path/format settings."""
    return settings.evidence


class LoggingContainer(containers.DeclarativeContainer):
    """Logging and forensic audit trail providers."""

    settings = providers.Dependency(instance_of=DFATSettings)

    forensic_audit_logger = providers.Singleton(
        ForensicAuditLogger,
        audit_log_path=providers.Callable(_audit_log_path, settings),
        hash_algorithm=providers.Callable(_primary_hash, settings),
    )

    setup_app_logging = providers.Callable(
        setup_logging,
        settings=providers.Callable(_logging_settings, settings),
    )


class StorageContainer(containers.DeclarativeContainer):
    """Local and secure storage providers."""

    settings = providers.Dependency(instance_of=DFATSettings)

    local_storage = providers.Singleton(
        LocalFileStorage,
        base_dir=providers.Callable(_evidence_dir, settings),
    )
    secure_storage = providers.Singleton(
        SecureStorage,
        base_dir=providers.Callable(_output_dir, settings),
    )


class RepositoryContainer(containers.DeclarativeContainer):
    """Persistence repository providers (file fallbacks + SQLAlchemy)."""

    local_storage = providers.Dependency(instance_of=LocalFileStorage)
    secure_storage = providers.Dependency(instance_of=SecureStorage)
    session_factory = providers.Dependency()

    # File-based fallbacks (sync pipeline / offline testing).
    file_evidence_repo = providers.Singleton(
        FileSystemEvidenceRepository,
        storage=local_storage,
    )
    file_artefact_repo = providers.Singleton(
        JSONArtefactRepository,
        storage=local_storage,
    )
    file_report_repo = providers.Singleton(
        FileSystemReportRepository,
        storage=secure_storage,
    )

    # Primary SQLAlchemy-backed repositories (async).
    evidence_repo = providers.Singleton(
        SQLAlchemyEvidenceRepository,
        session_factory=session_factory,
    )
    artefact_repo = providers.Singleton(
        SQLAlchemyArtefactRepository,
        session_factory=session_factory,
    )
    report_repo = providers.Singleton(
        SQLAlchemyReportRepository,
        session_factory=session_factory,
    )
    user_repo = providers.Singleton(
        SQLAlchemyUserRepository,
        session_factory=session_factory,
    )
    session_repo = providers.Singleton(
        SessionRepository,
        session_factory=session_factory,
    )
    audit_repo = providers.Singleton(
        SQLAlchemyAuditRepository,
        session_factory=session_factory,
    )
    benchmark_repo = providers.Singleton(
        SQLAlchemyBenchmarkRepository,
        session_factory=session_factory,
    )
    usability_repo = providers.Singleton(
        SQLAlchemyUsabilityRepository,
        session_factory=session_factory,
    )
    case_repo = providers.Singleton(
        SQLAlchemyCaseRepository,
        session_factory=session_factory,
    )
    custody_repo = providers.Singleton(
        CustodyRepository,
        session_factory=session_factory,
    )
    evidence_status_repo = providers.Singleton(
        EvidenceStatusRepository,
        session_factory=session_factory,
    )
    evidence_metadata_repo = providers.Singleton(
        EvidenceMetadataRepository,
        session_factory=session_factory,
    )
    pipeline_repo = providers.Singleton(
        SQLAlchemyPipelineRepository,
        session_factory=session_factory,
    )
    ai_analysis_repo = providers.Singleton(
        SQLAlchemyAIAnalysisRepository,
        session_factory=session_factory,
    )


def _volatility_symbols_path(settings: DFATSettings) -> Path | None:
    """Extract optional Volatility symbols path from settings."""
    return settings.forensic_engine.volatility_symbols_path


def _plugin_executor_timeout(settings: DFATSettings) -> int:
    """Extract Volatility plugin timeout from pipeline settings."""
    return int(settings.pipeline.volatility_plugins_timeout)


def _enable_memory_registry(settings: DFATSettings) -> bool:
    """Return whether the memory registry (hivelist/printkey) parser is enabled."""
    return bool(settings.pipeline.enable_memory_registry)


def _build_forensic_parsers(
    filesystem_parser: IArtefactParser,
    registry_parser: IArtefactParser,
    browser_parser: IArtefactParser,
    eventlog_parser: IArtefactParser,
    process_parser: IArtefactParser,
    network_parser: IArtefactParser,
    injection_parser: IArtefactParser,
    memory_registry_parser: IArtefactParser,
    enable_memory_registry: bool,
) -> list[IArtefactParser]:
    """Assemble the artefact parser list for registry and orchestrator wiring.

    Always includes disk parsers and the three core memory parsers
    (process, network, injection). ``MemoryRegistryParser`` is included only
    when ``enable_memory_registry`` is ``True``.
    """
    parsers: list[IArtefactParser] = [
        filesystem_parser,
        registry_parser,
        browser_parser,
        eventlog_parser,
        process_parser,
        network_parser,
        injection_parser,
    ]
    if enable_memory_registry:
        parsers.append(memory_registry_parser)
    return parsers


class CacheContainer(containers.DeclarativeContainer):
    """In-memory artefact cache providers."""

    artefact_cache = providers.Singleton(InMemoryArtefactCache, max_size=100)


class ForensicEngineContainer(containers.DeclarativeContainer):
    """Forensic acquisition/parsing engine providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)
    local_storage = providers.Dependency(instance_of=LocalFileStorage)

    integrity_checker = providers.Singleton(
        IntegrityChecker,
        audit_logger=audit_logger,
        hash_algorithm=providers.Callable(_primary_hash, settings),
    )
    multi_hash_service = providers.Singleton(
        MultiHashService,
        audit_logger=audit_logger,
    )
    image_handler = providers.Singleton(
        DiskImageHandler,
        integrity_checker=integrity_checker,
        audit_logger=audit_logger,
        storage=local_storage,
    )
    disk_image_accessor = providers.Singleton(
        DiskImageAccessor,
        audit_logger=audit_logger,
    )
    memory_handler = providers.Singleton(
        MemoryDumpHandler,
        integrity_checker=integrity_checker,
        audit_logger=audit_logger,
        storage=local_storage,
        volatility_symbols_path=providers.Callable(_volatility_symbols_path, settings),
    )
    volatility_runner = providers.Singleton(
        VolatilityRunner,
        symbols_path=providers.Callable(_volatility_symbols_path, settings),
        audit_logger=audit_logger,
    )
    plugin_executor = providers.Factory(
        PluginExecutor,
        volatility_runner=volatility_runner,
        audit_logger=audit_logger,
        timeout_seconds=providers.Callable(_plugin_executor_timeout, settings),
    )
    filesystem_parser = providers.Singleton(
        FileSystemParser,
        disk_accessor=disk_image_accessor,
        audit_logger=audit_logger,
    )
    registry_parser = providers.Singleton(
        RegistryParser,
        disk_accessor=disk_image_accessor,
        audit_logger=audit_logger,
    )
    browser_parser = providers.Singleton(
        BrowserHistoryParser,
        disk_accessor=disk_image_accessor,
        audit_logger=audit_logger,
    )
    eventlog_parser = providers.Singleton(
        EventLogParser,
        disk_accessor=disk_image_accessor,
        audit_logger=audit_logger,
    )
    process_parser = providers.Singleton(
        ProcessListParser,
        plugin_executor=plugin_executor,
        audit_logger=audit_logger,
    )
    network_parser = providers.Singleton(
        NetworkArtefactParser,
        plugin_executor=plugin_executor,
        audit_logger=audit_logger,
    )
    injection_parser = providers.Singleton(
        CodeInjectionParser,
        plugin_executor=plugin_executor,
        audit_logger=audit_logger,
    )
    memory_registry_parser = providers.Singleton(
        MemoryRegistryParser,
        plugin_executor=plugin_executor,
        audit_logger=audit_logger,
    )
    normalizer = providers.Singleton(ArtefactNormalizer)
    parsers = providers.Factory(
        _build_forensic_parsers,
        filesystem_parser=filesystem_parser,
        registry_parser=registry_parser,
        browser_parser=browser_parser,
        eventlog_parser=eventlog_parser,
        process_parser=process_parser,
        network_parser=network_parser,
        injection_parser=injection_parser,
        memory_registry_parser=memory_registry_parser,
        enable_memory_registry=providers.Callable(_enable_memory_registry, settings),
    )
    orchestrator = providers.Singleton(
        ForensicOrchestrator,
        parsers=parsers,
        normalizer=normalizer,
        integrity_checker=integrity_checker,
        disk_handler=image_handler,
        memory_handler=memory_handler,
        audit_logger=audit_logger,
    )


def _ollama_base_url(api_url: str) -> str:
    """Derive Ollama base URL from a base or ``/api/generate`` endpoint."""
    parsed = urlparse(api_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return api_url.rstrip("/")


def _llm_config(settings: DFATSettings) -> LLMConfig:
    """Build ``LLMConfig`` from application settings."""
    ai: AIEngineSettings = settings.ai_engine
    return LLMConfig(
        api_url=_ollama_base_url(ai.llm_api_url),
        model=ai.llm_model,
        temperature=ai.temperature,
        max_tokens=ai.max_tokens,
        request_timeout_seconds=ai.request_timeout_seconds,
        context_window=ai.context_window,
        max_retries=ai.max_retries,
        retry_delay_seconds=ai.retry_delay_seconds,
        num_predict=min(ai.max_tokens, 2048),
    )


def _enable_fallback(settings: DFATSettings) -> bool:
    """Extract fallback toggle from settings."""
    return settings.ai_engine.enable_fallback


class _NullAuditService:
    """No-op audit port used when wiring AIMonitor before ServicesContainer."""

    async def log_action(self, *args: Any, **kwargs: Any) -> None:
        return None


class AIEngineContainer(containers.DeclarativeContainer):
    """AI triage engine providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)

    llm_config = providers.Singleton(_llm_config, settings)
    connection_manager = providers.Singleton(
        LLMConnectionManager,
        config=llm_config,
        audit_logger=audit_logger,
    )
    ollama_client = providers.Singleton(
        OllamaClient,
        config=llm_config,
        connection_manager=connection_manager,
        audit_logger=audit_logger,
    )
    prompts = providers.Singleton(ForensicPromptTemplates)
    artefact_serializer = providers.Singleton(ArtefactSerializer)
    artefact_batcher = providers.Singleton(
        ArtefactBatcher,
        max_tokens_per_batch=6000,
        serializer=artefact_serializer,
    )
    classification_prompt_builder = providers.Singleton(
        ClassificationPromptBuilder,
        templates=prompts,
        serializer=artefact_serializer,
        batcher=artefact_batcher,
    )
    classification_response_parser = providers.Singleton(ClassificationResponseParser)
    classification_confidence = providers.Singleton(ClassificationDefaultConfidenceScorer)
    llm_artefact_classifier = providers.Singleton(
        LLMArtefactClassifier,
        ollama_client=ollama_client,
        prompt_builder=classification_prompt_builder,
        response_parser=classification_response_parser,
        confidence_scorer=classification_confidence,
        audit_logger=audit_logger,
        config=llm_config,
    )
    ranking_prompt_builder = providers.Singleton(
        RankingPromptBuilder,
        templates=prompts,
        serializer=artefact_serializer,
    )
    ranking_response_parser = providers.Singleton(RankingResponseParser)
    llm_relevance_ranker = providers.Singleton(
        LLMRelevanceRanker,
        ollama_client=ollama_client,
        prompt_builder=ranking_prompt_builder,
        response_parser=ranking_response_parser,
        audit_logger=audit_logger,
        config=llm_config,
    )
    summarization_prompt_builder = providers.Singleton(
        SummarizationPromptBuilder,
        templates=prompts,
        serializer=artefact_serializer,
    )
    summary_response_validator = providers.Singleton(SummaryResponseValidator)
    llm_investigative_summarizer = providers.Singleton(
        LLMInvestigativeSummarizer,
        ollama_client=ollama_client,
        prompt_builder=summarization_prompt_builder,
        response_validator=summary_response_validator,
        audit_logger=audit_logger,
        config=llm_config,
    )
    confidence_scorer = providers.Singleton(ConfidenceScorer)
    hallucination_guard = providers.Singleton(AIResponseValidator.default_guard)
    ai_response_validator = providers.Singleton(
        AIResponseValidator,
        hallucination_guard=hallucination_guard,
        confidence_scorer=confidence_scorer,
    )
    ai_response_cache = providers.Singleton(
        AIResponseCache,
        max_size=1000,
        ttl_seconds=3600,
    )
    ai_monitor = providers.Singleton(
        AIMonitor,
        audit_service=providers.Factory(_NullAuditService),
        app_logger=providers.Object(None),
    )
    llm_client = providers.Singleton(
        LocalLLMClient,
        config=llm_config,
        ollama_client=ollama_client,
        connection_manager=connection_manager,
        classifier=llm_artefact_classifier,
        ranker=llm_relevance_ranker,
        summarizer=llm_investigative_summarizer,
        validator=ai_response_validator,
        cache=ai_response_cache,
        monitor=ai_monitor,
        audit_logger=audit_logger,
    )
    fallback = providers.Singleton(
        RuleBasedAnalyzer,
        audit_logger=audit_logger,
    )
    classifier = providers.Singleton(
        ArtefactClassifier,
        llm_client=llm_client,
    )
    ranker = providers.Singleton(RelevanceRanker)
    summarizer = providers.Singleton(
        InvestigativeSummarizer,
        llm_client=llm_client,
    )
    active_analyzer = providers.Factory(
        select_analyzer,
        llm_client=llm_client,
        fallback=fallback,
        enable_fallback=providers.Callable(_enable_fallback, settings),
    )


_PACKAGE_TEMPLATE_DIR = Path(__file__).resolve().parent / "reporting" / "templates"
_PACKAGE_SCHEMA_DIR = Path(__file__).resolve().parent / "reporting" / "schema"


def _report_schema_path(settings: DFATSettings) -> Path:
    """Resolve the JSON report schema path (canonical schema package preferred)."""
    configured = Path(settings.reporting.template_dir) / "report_schema.json"
    if configured.exists():
        return configured
    canonical = _PACKAGE_SCHEMA_DIR / "report_schema.json"
    if canonical.exists():
        return canonical
    try:
        return _canonical_schema_path()
    except KeyError:
        return _PACKAGE_TEMPLATE_DIR / "report_schema.json"


def _template_dir(settings: DFATSettings) -> Path:
    """Resolve the narrative template directory."""
    configured = Path(settings.reporting.template_dir)
    if configured.exists():
        return configured
    return _PACKAGE_TEMPLATE_DIR


class ReportingEngineContainer(containers.DeclarativeContainer):
    """Dual-output reporting engine providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)
    report_repo = providers.Dependency(instance_of=FileSystemReportRepository)
    audit_repo = providers.Dependency(instance_of=SQLAlchemyAuditRepository)

    audit_service = providers.Factory(
        AuditService,
        audit_repo=audit_repo,
        forensic_audit_logger=audit_logger,
    )
    schema_validator = providers.Singleton(
        ReportSchemaValidator,
        schema_path=providers.Callable(_report_schema_path, settings),
    )
    json_exporter = providers.Singleton(
        StructuredJSONExporter,
        schema_validator=schema_validator,
        hash_algorithm=providers.Callable(_primary_hash, settings),
    )
    narrative_assembler = providers.Singleton(
        NarrativeAssembler,
        template_dir=providers.Callable(_template_dir, settings),
    )
    integrity_verifier = providers.Singleton(
        ReportIntegrityVerifier,
        hash_algorithm=providers.Callable(_primary_hash, settings),
    )
    reproducibility_verifier = providers.Singleton(
        ReproducibilityVerifier,
        hash_algorithm=providers.Callable(_primary_hash, settings),
    )
    report_builder = providers.Singleton(
        DualOutputReportBuilder,
        json_exporter=json_exporter,
        narrative_assembler=narrative_assembler,
        integrity_verifier=integrity_verifier,
        report_repo=report_repo,
        audit_service=audit_service,
    )
    # Same provider exposed under the IReportGenerator port name.
    report_generator: providers.Provider[IReportGenerator] = report_builder
    pdf_exporter = providers.Singleton(
        PDFReportExporter,
        output_dir=providers.Callable(_output_dir, settings),
    )
    html_exporter = providers.Singleton(
        HTMLReportExporter,
        output_dir=providers.Callable(_output_dir, settings),
        template_dir=providers.Callable(_template_dir, settings),
    )
    json_file_exporter = providers.Singleton(
        JSONFileExporter,
        integrity_verifier=integrity_verifier,
    )


def _ground_truth_dir(settings: DFATSettings) -> Path:
    """Extract ground-truth directory from settings."""
    return settings.evaluation.ground_truth_dir


def _metric_thresholds(settings: DFATSettings) -> dict[str, float]:
    """Extract evaluation metric thresholds from settings."""
    thresholds = settings.evaluation.metrics_thresholds
    return {
        "precision_min": float(thresholds.get("precision_min", 0.0)),
        "recall_min": float(thresholds.get("recall_min", 0.0)),
        "f1_min": float(thresholds.get("f1_min", 0.0)),
    }


class EvaluationEngineContainer(containers.DeclarativeContainer):
    """Benchmark and usability evaluation providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)
    audit_repo = providers.Dependency(instance_of=SQLAlchemyAuditRepository)
    benchmark_repo = providers.Dependency(instance_of=SQLAlchemyBenchmarkRepository)
    usability_repo = providers.Dependency(instance_of=SQLAlchemyUsabilityRepository)

    dfrws_handler = providers.Singleton(
        DFRWSHandler,
        datasets_dir=providers.Callable(_ground_truth_dir, settings),
    )
    cfreds_handler = providers.Singleton(
        CFReDSHandler,
        datasets_dir=providers.Callable(_ground_truth_dir, settings),
    )
    ground_truth_loader = providers.Singleton(
        GroundTruthLoader,
        ground_truth_dir=providers.Callable(_ground_truth_dir, settings),
        dfrws=dfrws_handler,
        cfreds=cfreds_handler,
    )
    metrics_calculator = providers.Singleton(MetricsCalculator)
    audit_service = providers.Factory(
        AuditService,
        audit_repo=audit_repo,
        forensic_audit_logger=audit_logger,
    )
    comparator = providers.Singleton(
        BenchmarkComparator,
        metrics=metrics_calculator,
        ground_truth_loader=ground_truth_loader,
        audit_service=audit_service,
        benchmark_repo=benchmark_repo,
        thresholds=providers.Callable(_metric_thresholds, settings),
    )
    metrics_visualiser = providers.Singleton(MetricsVisualiser)
    performance_analyzer = providers.Singleton(
        PerformanceAnalyzer,
        benchmark_repo=benchmark_repo,
    )
    questionnaire_model = providers.Singleton(QuestionnaireInstrument)
    response_collector = providers.Singleton(
        ResponseCollector,
        questionnaire=questionnaire_model,
        usability_repo=usability_repo,
        audit_service=audit_service,
    )
    response_analyzer = providers.Factory(ResponseAnalyzer)


def _pipeline_max_concurrent(settings: DFATSettings) -> int:
    """Extract max concurrent pipeline jobs from settings."""
    return settings.pipeline.max_concurrent_jobs


def _pipeline_app_logger() -> Any:
    """Return a structlog bound logger for pipeline events."""
    import structlog

    return structlog.get_logger("dfat.pipeline")


def _build_parser_registry(parsers: list[IArtefactParser]) -> ParserRegistry:
    """Populate a ``ParserRegistry`` from the forensic engine parser list."""
    registry = ParserRegistry()
    for parser in parsers:
        registry.register(parser)
    return registry


def _parser_timeout_seconds(settings: DFATSettings) -> float:
    """Extract per-parser timeout from pipeline settings."""
    return float(settings.pipeline.parser_timeout_seconds)


def _build_stage_registry(
    acquisition_stage: AcquisitionStage,
    parsing_stage: ParsingStage,
    triage_stage: TriageStage,
    reporting_stage: ReportingStage,
    evaluation_stage: EvaluationStage,
) -> StageRegistry:
    """Create a stage registry with all five pipeline stages registered."""
    registry = StageRegistry()
    registry.register(acquisition_stage)
    registry.register(parsing_stage)
    registry.register(triage_stage)
    registry.register(reporting_stage)
    registry.register(evaluation_stage)
    return registry


class PipelineContainer(containers.DeclarativeContainer):
    """Top-level pipeline orchestration providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    forensic_orchestrator = providers.Dependency(instance_of=ForensicOrchestrator)
    analyzer = providers.Dependency()
    llm_analyzer = providers.Dependency()
    fallback_analyzer = providers.Dependency(instance_of=RuleBasedAnalyzer)
    report_builder = providers.Dependency(instance_of=DualOutputReportBuilder)
    evidence_repo = providers.Dependency(instance_of=FileSystemEvidenceRepository)
    report_repo = providers.Dependency(instance_of=FileSystemReportRepository)
    ground_truth_loader = providers.Dependency(instance_of=GroundTruthLoader)
    benchmark_comparator = providers.Dependency(instance_of=BenchmarkComparator)
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)
    audit_repo = providers.Dependency(instance_of=SQLAlchemyAuditRepository)
    sqlalchemy_evidence_repo = providers.Dependency(
        instance_of=SQLAlchemyEvidenceRepository
    )
    disk_handler = providers.Dependency(instance_of=DiskImageHandler)
    memory_handler = providers.Dependency(instance_of=MemoryDumpHandler)
    integrity_checker = providers.Dependency(instance_of=IntegrityChecker)
    multi_hash_service = providers.Dependency(instance_of=MultiHashService)
    artefact_parsers = providers.Dependency()
    artefact_normalizer = providers.Dependency(instance_of=ArtefactNormalizer)
    evidence_management_service = providers.Dependency(
        instance_of=EvidenceManagementService
    )
    custody_service = providers.Dependency(instance_of=ChainOfCustodyService)
    case_repo = providers.Dependency(instance_of=SQLAlchemyCaseRepository)
    pipeline_repo = providers.Dependency(instance_of=SQLAlchemyPipelineRepository)

    pipeline_settings = providers.Callable(_pipeline_settings, settings)
    pipeline_audit_service = providers.Factory(
        AuditService,
        audit_repo=audit_repo,
        forensic_audit_logger=audit_logger,
    )
    progress_tracker = providers.Singleton(ProgressTracker)
    pipeline_logger = providers.Factory(
        PipelineLogger,
        audit_service=pipeline_audit_service,
        app_logger=providers.Callable(_pipeline_app_logger),
    )
    pipeline_error_handler = providers.Factory(
        PipelineErrorHandler,
        pipeline_logger=pipeline_logger,
    )
    evidence_discovery_service = providers.Factory(
        EvidenceDiscoveryService,
        evidence_settings=providers.Callable(_evidence_settings, settings),
        evidence_repo=sqlalchemy_evidence_repo,
        audit_service=pipeline_audit_service,
    )
    evidence_loader = providers.Factory(
        EvidenceLoader,
        disk_handler=disk_handler,
        memory_handler=memory_handler,
        integrity_checker=integrity_checker,
        hash_service=multi_hash_service,
        audit_service=pipeline_audit_service,
    )
    acquisition_stage = providers.Factory(
        AcquisitionStage,
        evidence_loader=evidence_loader,
        evidence_management_service=evidence_management_service,
        custody_service=custody_service,
        progress_tracker=progress_tracker,
        audit_service=pipeline_audit_service,
    )
    parser_registry = providers.Singleton(
        _build_parser_registry,
        parsers=artefact_parsers,
    )
    evidence_router = providers.Factory(
        EvidenceRouter,
        parser_registry=parser_registry,
    )
    parsing_stage = providers.Factory(
        ParsingStage,
        parser_registry=parser_registry,
        evidence_router=evidence_router,
        normalizer=artefact_normalizer,
        progress_tracker=progress_tracker,
        error_handler=pipeline_error_handler,
        audit_service=pipeline_audit_service,
        parser_timeout_seconds=providers.Callable(_parser_timeout_seconds, settings),
    )

    # Artefact processing + triage providers (Stage 3).
    artefact_categoriser = providers.Singleton(ArtefactCategoriser)
    artefact_standardiser = providers.Singleton(ArtefactStandardiser)
    artefact_deduplicator = providers.Singleton(ArtefactDeduplicator)
    artefact_correlator = providers.Singleton(ArtefactCorrelator)
    relationship_mapper = providers.Singleton(RelationshipMapper)
    timeline_generator = providers.Singleton(TimelineGenerator)
    ioc_detector = providers.Singleton(IOCDetector)
    scoring_engine = providers.Singleton(ScoringEngine)
    rule_based_triage_engine = providers.Singleton(
        RuleBasedTriageEngine,
        scoring_engine=scoring_engine,
    )
    triage_aggregator = providers.Singleton(TriageAggregator)
    triage_stage = providers.Factory(
        TriageStage,
        ioc_detector=ioc_detector,
        scoring_engine=scoring_engine,
        rule_engine=rule_based_triage_engine,
        triage_aggregator=triage_aggregator,
        llm_analyzer=llm_analyzer,
        fallback_analyzer=fallback_analyzer,
        progress_tracker=progress_tracker,
        audit_service=pipeline_audit_service,
        settings=settings,
        categoriser=artefact_categoriser,
        standardiser=artefact_standardiser,
        deduplicator=artefact_deduplicator,
        correlator=artefact_correlator,
        relationship_mapper=relationship_mapper,
        timeline_generator=timeline_generator,
    )
    reporting_stage = providers.Factory(
        ReportingStage,
        report_builder=report_builder,
        progress_tracker=progress_tracker,
        audit_service=pipeline_audit_service,
    )
    evaluation_stage = providers.Factory(
        EvaluationStage,
        benchmark_comparator=benchmark_comparator,
        ground_truth_loader=ground_truth_loader,
        progress_tracker=progress_tracker,
        audit_service=pipeline_audit_service,
        settings=settings,
    )
    stage_registry = providers.Singleton(
        _build_stage_registry,
        acquisition_stage=acquisition_stage,
        parsing_stage=parsing_stage,
        triage_stage=triage_stage,
        reporting_stage=reporting_stage,
        evaluation_stage=evaluation_stage,
    )
    job_manager = providers.Singleton(
        JobManager,
        audit_service=pipeline_audit_service,
        max_concurrent=providers.Callable(_pipeline_max_concurrent, settings),
    )
    job_runner = providers.Factory(
        JobRunner,
        job_manager=job_manager,
        stage_registry=stage_registry,
        audit_service=pipeline_audit_service,
    )

    pipeline_orchestrator = providers.Singleton(
        PipelineOrchestrator,
        stage_registry=stage_registry,
        job_manager=job_manager,
        job_runner=job_runner,
        progress_tracker=progress_tracker,
        pipeline_logger=pipeline_logger,
        evidence_repo=sqlalchemy_evidence_repo,
        case_repo=case_repo,
        audit_service=pipeline_audit_service,
        settings=settings,
        evidence_management_service=evidence_management_service,
        custody_service=custody_service,
        ground_truth_loader=ground_truth_loader,
        benchmark_comparator=benchmark_comparator,
        pipeline_repo=pipeline_repo,
        parser_registry=parser_registry,
    )


class DatabaseContainer(containers.DeclarativeContainer):
    """Async SQLAlchemy persistence providers."""

    settings = providers.Dependency(instance_of=DFATSettings)

    database_engine = providers.Singleton(
        DatabaseEngine,
        database_url=providers.Callable(_database_url, settings),
        echo=providers.Callable(_database_echo, settings),
        pool_size=providers.Callable(_database_pool_size, settings),
        max_overflow=providers.Callable(_database_max_overflow, settings),
    )
    session_factory = providers.Callable(
        lambda engine: engine.session_factory,
        database_engine,
    )


class AuthContainer(containers.DeclarativeContainer):
    """Authentication primitive providers."""

    settings = providers.Dependency(instance_of=DFATSettings)

    password_hasher = providers.Singleton(PasswordHasher)
    jwt_handler = providers.Singleton(
        JWTHandler,
        secret_key=providers.Callable(_auth_secret_key, settings),
        algorithm=providers.Callable(_auth_algorithm, settings),
        access_token_expire_minutes=providers.Callable(_auth_access_expire, settings),
        refresh_token_expire_days=providers.Callable(_auth_refresh_expire, settings),
    )
    permission_checker = providers.Singleton(PermissionChecker)


class ServicesContainer(containers.DeclarativeContainer):
    """Application service-layer providers (business logic)."""

    settings = providers.Dependency(instance_of=DFATSettings)
    user_repo = providers.Dependency(instance_of=SQLAlchemyUserRepository)
    session_repo = providers.Dependency(instance_of=SessionRepository)
    audit_repo = providers.Dependency(instance_of=SQLAlchemyAuditRepository)
    evidence_repo = providers.Dependency(instance_of=SQLAlchemyEvidenceRepository)
    artefact_repo = providers.Dependency(instance_of=SQLAlchemyArtefactRepository)
    report_repo = providers.Dependency(instance_of=SQLAlchemyReportRepository)
    benchmark_repo = providers.Dependency(instance_of=SQLAlchemyBenchmarkRepository)
    usability_repo = providers.Dependency(instance_of=SQLAlchemyUsabilityRepository)
    case_repo = providers.Dependency(instance_of=SQLAlchemyCaseRepository)
    custody_repo = providers.Dependency(instance_of=CustodyRepository)
    evidence_status_repo = providers.Dependency(instance_of=EvidenceStatusRepository)
    evidence_metadata_repo = providers.Dependency(instance_of=EvidenceMetadataRepository)
    password_hasher = providers.Dependency(instance_of=PasswordHasher)
    jwt_handler = providers.Dependency(instance_of=JWTHandler)
    integrity_checker = providers.Dependency(instance_of=IntegrityChecker)
    multi_hash_service = providers.Dependency(instance_of=MultiHashService)
    disk_handler = providers.Dependency(instance_of=DiskImageHandler)
    memory_handler = providers.Dependency(instance_of=MemoryDumpHandler)
    local_storage = providers.Dependency(instance_of=LocalFileStorage)
    pipeline_orchestrator = providers.Dependency(instance_of=PipelineOrchestrator)
    benchmark_comparator = providers.Dependency(instance_of=BenchmarkComparator)
    ground_truth_loader = providers.Dependency(instance_of=GroundTruthLoader)
    forensic_audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)
    pdf_exporter = providers.Dependency(instance_of=PDFReportExporter)
    html_exporter = providers.Dependency(instance_of=HTMLReportExporter)
    json_file_exporter = providers.Dependency(instance_of=JSONFileExporter)
    integrity_verifier = providers.Dependency(instance_of=ReportIntegrityVerifier)
    reproducibility_verifier = providers.Dependency(instance_of=ReproducibilityVerifier)
    response_collector = providers.Dependency(instance_of=ResponseCollector)
    performance_analyzer = providers.Dependency(instance_of=PerformanceAnalyzer)
    questionnaire_model = providers.Dependency(instance_of=QuestionnaireInstrument)

    mime_identifier = providers.Singleton(MIMEIdentifier)
    evidence_metadata_service = providers.Factory(
        EvidenceMetadataService,
        metadata_repo=evidence_metadata_repo,
        hash_service=multi_hash_service,
        mime_identifier=mime_identifier,
    )
    evidence_validation_service = providers.Factory(
        EvidenceValidationService,
        mime_identifier=mime_identifier,
        hash_service=multi_hash_service,
        evidence_status_repo=evidence_status_repo,
        audit_logger=forensic_audit_logger,
        settings=settings,
        evidence_metadata_repo=evidence_metadata_repo,
    )
    audit_service = providers.Factory(
        AuditService,
        audit_repo=audit_repo,
        forensic_audit_logger=forensic_audit_logger,
    )
    chain_of_custody_service = providers.Factory(
        ChainOfCustodyService,
        custody_repo=custody_repo,
        hash_service=multi_hash_service,
        audit_service=audit_service,
        evidence_repo=evidence_repo,
    )
    custody_report_generator = providers.Factory(
        CustodyReportGenerator,
        custody_service=chain_of_custody_service,
        hash_service=multi_hash_service,
        template_dir=providers.Callable(_template_dir, settings),
    )
    audit_report_generator = providers.Factory(
        AuditReportGenerator,
        audit_service=audit_service,
    )
    case_service = providers.Factory(
        CaseService,
        case_repo=case_repo,
        evidence_repo=evidence_repo,
        user_repo=user_repo,
        audit_service=audit_service,
        custody_service=chain_of_custody_service,
    )

    user_service = providers.Factory(
        UserService,
        user_repo=user_repo,
        session_repo=session_repo,
        password_hasher=password_hasher,
        jwt_handler=jwt_handler,
        audit_repo=audit_repo,
        auth_settings=providers.Callable(_auth_settings, settings),
    )
    evidence_service = providers.Factory(
        EvidenceService,
        evidence_repo=evidence_repo,
        integrity_checker=integrity_checker,
        disk_handler=disk_handler,
        memory_handler=memory_handler,
        audit_repo=audit_repo,
        storage=local_storage,
    )
    evidence_management_service = providers.Factory(
        EvidenceManagementService,
        evidence_service=evidence_service,
        validation_service=evidence_validation_service,
        hash_service=multi_hash_service,
        custody_service=chain_of_custody_service,
        metadata_repo=evidence_metadata_repo,
        status_repo=evidence_status_repo,
        evidence_repo=evidence_repo,
        case_repo=case_repo,
        audit_service=audit_service,
    )
    analysis_service = providers.Factory(
        AnalysisService,
        pipeline_orchestrator=pipeline_orchestrator,
        evidence_repo=evidence_repo,
        artefact_repo=artefact_repo,
        report_repo=report_repo,
        audit_repo=audit_repo,
        integrity_checker=integrity_checker,
    )
    report_service = providers.Factory(
        ReportService,
        report_repo=report_repo,
        audit_repo=audit_repo,
        pdf_exporter=pdf_exporter,
        html_exporter=html_exporter,
        json_file_exporter=json_file_exporter,
        integrity_verifier=integrity_verifier,
        reproducibility_verifier=reproducibility_verifier,
        custody_report_generator=custody_report_generator,
        audit_report_generator=audit_report_generator,
        case_repo=case_repo,
        evidence_repo=evidence_repo,
        export_dir=providers.Callable(_output_dir, settings),
    )
    evaluation_service = providers.Factory(
        EvaluationService,
        benchmark_repo=benchmark_repo,
        usability_repo=usability_repo,
        benchmark_comparator=benchmark_comparator,
        ground_truth_loader=ground_truth_loader,
        audit_repo=audit_repo,
        artefact_repo=artefact_repo,
        response_collector=response_collector,
        performance_analyzer=performance_analyzer,
        questionnaire=questionnaire_model,
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """Root application DI container with nested engine sub-containers."""

    config = providers.Configuration()
    settings = providers.Singleton(load_settings)

    logging = providers.Container(LoggingContainer, settings=settings)
    storage = providers.Container(StorageContainer, settings=settings)
    database = providers.Container(DatabaseContainer, settings=settings)
    repositories = providers.Container(
        RepositoryContainer,
        local_storage=storage.local_storage,
        secure_storage=storage.secure_storage,
        session_factory=database.session_factory,
    )
    auth = providers.Container(AuthContainer, settings=settings)
    cache = providers.Container(CacheContainer)
    forensic_engine = providers.Container(
        ForensicEngineContainer,
        settings=settings,
        audit_logger=logging.forensic_audit_logger,
        local_storage=storage.local_storage,
    )
    ai_engine = providers.Container(
        AIEngineContainer,
        settings=settings,
        audit_logger=logging.forensic_audit_logger,
    )
    reporting_engine = providers.Container(
        ReportingEngineContainer,
        settings=settings,
        audit_logger=logging.forensic_audit_logger,
        report_repo=repositories.file_report_repo,
        audit_repo=repositories.audit_repo,
    )
    evaluation_engine = providers.Container(
        EvaluationEngineContainer,
        settings=settings,
        audit_logger=logging.forensic_audit_logger,
        audit_repo=repositories.audit_repo,
        benchmark_repo=repositories.benchmark_repo,
        usability_repo=repositories.usability_repo,
    )
    pipeline = providers.Container(
        PipelineContainer,
        settings=settings,
        forensic_orchestrator=forensic_engine.orchestrator,
        analyzer=ai_engine.active_analyzer,
        llm_analyzer=ai_engine.llm_client,
        fallback_analyzer=ai_engine.fallback,
        report_builder=reporting_engine.report_builder,
        evidence_repo=repositories.file_evidence_repo,
        report_repo=repositories.file_report_repo,
        ground_truth_loader=evaluation_engine.ground_truth_loader,
        benchmark_comparator=evaluation_engine.comparator,
        audit_logger=logging.forensic_audit_logger,
        audit_repo=repositories.audit_repo,
        sqlalchemy_evidence_repo=repositories.evidence_repo,
        case_repo=repositories.case_repo,
        pipeline_repo=repositories.pipeline_repo,
        disk_handler=forensic_engine.image_handler,
        memory_handler=forensic_engine.memory_handler,
        integrity_checker=forensic_engine.integrity_checker,
        multi_hash_service=forensic_engine.multi_hash_service,
        artefact_parsers=forensic_engine.parsers,
        artefact_normalizer=forensic_engine.normalizer,
    )

    services = providers.Container(
        ServicesContainer,
        settings=settings,
        user_repo=repositories.user_repo,
        session_repo=repositories.session_repo,
        audit_repo=repositories.audit_repo,
        evidence_repo=repositories.evidence_repo,
        artefact_repo=repositories.artefact_repo,
        report_repo=repositories.report_repo,
        benchmark_repo=repositories.benchmark_repo,
        usability_repo=repositories.usability_repo,
        case_repo=repositories.case_repo,
        custody_repo=repositories.custody_repo,
        evidence_status_repo=repositories.evidence_status_repo,
        evidence_metadata_repo=repositories.evidence_metadata_repo,
        password_hasher=auth.password_hasher,
        jwt_handler=auth.jwt_handler,
        integrity_checker=forensic_engine.integrity_checker,
        multi_hash_service=forensic_engine.multi_hash_service,
        disk_handler=forensic_engine.image_handler,
        memory_handler=forensic_engine.memory_handler,
        local_storage=storage.local_storage,
        pipeline_orchestrator=pipeline.pipeline_orchestrator,
        benchmark_comparator=evaluation_engine.comparator,
        ground_truth_loader=evaluation_engine.ground_truth_loader,
        forensic_audit_logger=logging.forensic_audit_logger,
        pdf_exporter=reporting_engine.pdf_exporter,
        html_exporter=reporting_engine.html_exporter,
        json_file_exporter=reporting_engine.json_file_exporter,
        integrity_verifier=reporting_engine.integrity_verifier,
        reproducibility_verifier=reporting_engine.reproducibility_verifier,
        response_collector=evaluation_engine.response_collector,
        performance_analyzer=evaluation_engine.performance_analyzer,
        questionnaire_model=evaluation_engine.questionnaire_model,
    )


def build_application_container() -> ApplicationContainer:
    """Create the root DI container with cross-container dependencies wired.

    ``AcquisitionStage`` needs evidence-management / custody services that live
    in ``ServicesContainer``, while services need ``pipeline_orchestrator``.
    Overrides break that cycle after both nested containers exist.
    """
    container = ApplicationContainer()
    container.pipeline.evidence_management_service.override(
        container.services.evidence_management_service
    )
    container.pipeline.custody_service.override(
        container.services.chain_of_custody_service
    )
    return container
