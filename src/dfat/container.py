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
from dfat.ai_engine.preprocessing.truncator import TokenTruncator
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
from dfat.monitoring.metrics_collector import MetricsCollector
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
from dfat.runtime.recovery_manager import RecoveryManager
from dfat.runtime.resource_tracker import ResourceTracker
from dfat.runtime.service_monitor import ServiceMonitor
from dfat.runtime.shutdown_handler import ShutdownHandler
from dfat.runtime.task_manager import BackgroundTaskManager
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
from dfat.bootstrap.ai_initializer import AIInitializer
from dfat.bootstrap.audit_initializer import AuditInitializer
from dfat.bootstrap.auth_initializer import AuthInitializer
from dfat.bootstrap.boot_sequencer import BootSequencer
from dfat.bootstrap.config_validator import ConfigurationValidator
from dfat.bootstrap.database_initializer import DatabaseInitializer
from dfat.bootstrap.dataset_initializer import DatasetInitializer
from dfat.bootstrap.directory_manager import DirectoryManager
from dfat.bootstrap.evaluation_initializer import EvaluationInitializer
from dfat.bootstrap.knowledge_initializer import KnowledgeInitializer
from dfat.bootstrap.parser_initializer import ParserInitializer
from dfat.bootstrap.reporting_initializer import ReportingInitializer
from dfat.bootstrap.threat_intel_initializer import ThreatIntelInitializer
from dfat.bootstrap.worker_initializer import WorkerInitializer
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
from dfat.database.repositories.dataset_repo import DatasetRepository
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
from dfat.dataset_intelligence.config import DatasetIntelligenceSettings
from dfat.dataset_intelligence.classifier import DatasetClassifier
from dfat.dataset_intelligence.preprocessor import DatasetPreprocessor
from dfat.dataset_intelligence.registry import DatasetRegistry
from dfat.dataset_intelligence.scanner import DatasetScanner
from dfat.dataset_intelligence.validator import DatasetValidator
from dfat.dataset_intelligence.watcher import DatasetWatcher
from dfat.knowledge.embeddings import LocalEmbeddingEngine
from dfat.knowledge.indexer import DocumentIndexer
from dfat.knowledge.ioc_database import IOCKnowledgeBase
from dfat.knowledge.knowledge_graph import ForensicKnowledgeGraph
from dfat.knowledge.rag.context_builder import RAGContextBuilder
from dfat.knowledge.rag.indexing_hooks import PipelineKnowledgeHooks
from dfat.knowledge.rag.rag_analyzer import RAGEnhancedAnalyzer
from dfat.knowledge.rag.rag_prompts import RAGPromptTemplates
from dfat.knowledge.retriever import UnifiedRetriever
from dfat.knowledge.vector_store import ForensicVectorStore
from dfat.ml.config import MLSettings
from dfat.ml.dataset_builder import MLDatasetBuilder
from dfat.ml.experiment_tracker import ExperimentTracker
from dfat.ml.feature_engineering import ForensicFeatureExtractor
from dfat.ml.model_registry import ModelRegistry
from dfat.ml.predictor import MLPredictor
from dfat.ml.retrainer import AutoRetrainer
from dfat.ml.trainer import ModelTrainer
from dfat.threat_intel.feed_manager import ThreatFeedManager
from dfat.threat_intel.mitre_mapper import MITREMapper
from dfat.threat_intel.sigma_engine import SigmaEngine
from dfat.threat_intel.stix_handler import STIXHandler
from dfat.threat_intel.yara_engine import YARAEngine
from dfat.settings import (
    AIEngineSettings,
    AuthSettings,
    DatabaseSettings,
    DatasetIntelligenceSettings as SettingsDatasetIntelligenceSettings,
    DFATSettings,
    EvidenceSettings,
    LoggingSettings,
    PipelineSettings,
    ReportingSettings,
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


def _database_settings(settings: DFATSettings) -> DatabaseSettings:
    """Extract database settings subsection."""
    return settings.database


def _reporting_settings(settings: DFATSettings) -> ReportingSettings:
    """Extract reporting settings subsection."""
    return settings.reporting


def _database_echo(settings: DFATSettings) -> bool:
    """Extract database SQL echo flag from settings."""
    return settings.database.echo


def _database_pool_size(settings: DFATSettings) -> int:
    """Extract database pool size from settings."""
    return settings.database.pool_size


def _database_max_overflow(settings: DFATSettings) -> int:
    """Extract database max overflow from settings."""
    return settings.database.max_overflow


def _database_enable_query_monitoring(settings: DFATSettings) -> bool:
    """Extract slow-query monitoring flag from settings."""
    return settings.database.enable_query_monitoring


def _database_slow_query_threshold_ms(settings: DFATSettings) -> int:
    """Extract slow-query duration threshold from settings."""
    return settings.database.slow_query_threshold_ms


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


def _dataset_intelligence_settings(
    settings: DFATSettings,
) -> SettingsDatasetIntelligenceSettings:
    """Extract nested dataset intelligence settings."""
    return settings.dataset_intelligence


def _ml_settings(settings: DFATSettings) -> MLSettings:
    """Extract nested ML lifecycle settings."""
    return settings.ml


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
    dataset_repo = providers.Singleton(
        DatasetRepository,
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


class KnowledgeContainer(containers.DeclarativeContainer):
    """Local embedding and vector-store providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    audit_service = providers.Dependency(instance_of=AuditService)
    dataset_repo = providers.Dependency(instance_of=DatasetRepository)

    dataset_intelligence_settings = providers.Callable(
        _dataset_intelligence_settings,
        settings,
    )
    vector_store_path = providers.Callable(
        lambda value: value.vector_store_path,
        dataset_intelligence_settings,
    )
    knowledge_graph_path = providers.Callable(
        lambda value: value.knowledge_graph_path,
        dataset_intelligence_settings,
    )
    ioc_database_path = providers.Callable(
        lambda value: value.ioc_database_path,
        dataset_intelligence_settings,
    )
    embedding_engine = providers.Singleton(LocalEmbeddingEngine)
    vector_store = providers.Singleton(
        ForensicVectorStore,
        persist_path=vector_store_path,
        embedding_engine=embedding_engine,
    )
    ioc_knowledge_base = providers.Singleton(
        IOCKnowledgeBase,
        db_path=ioc_database_path,
    )
    knowledge_graph = providers.Singleton(
        ForensicKnowledgeGraph,
        persist_path=knowledge_graph_path,
    )
    document_indexer = providers.Factory(
        DocumentIndexer,
        embedding_engine=embedding_engine,
        vector_store=vector_store,
        audit_service=audit_service,
        dataset_repo=dataset_repo,
    )
    unified_retriever = providers.Factory(
        UnifiedRetriever,
        vector_store=vector_store,
        ioc_db=ioc_knowledge_base,
        knowledge_graph=knowledge_graph,
        embedding_engine=embedding_engine,
    )
    token_truncator = providers.Singleton(TokenTruncator, max_tokens=6000)
    rag_prompts = providers.Singleton(RAGPromptTemplates)
    rag_context_builder = providers.Factory(
        RAGContextBuilder,
        retriever=unified_retriever,
        truncator=token_truncator,
    )
    pipeline_knowledge_hooks = providers.Factory(
        PipelineKnowledgeHooks,
        indexer=document_indexer,
        knowledge_graph=knowledge_graph,
        ioc_db=ioc_knowledge_base,
        audit_service=audit_service,
    )


class DatasetIntelligenceContainer(containers.DeclarativeContainer):
    """Dataset intelligence settings and path providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    audit_service = providers.Dependency(instance_of=AuditService)
    mime_identifier = providers.Dependency(instance_of=MIMEIdentifier)
    dataset_repo = providers.Dependency(instance_of=DatasetRepository)

    dataset_intelligence_settings = providers.Callable(
        _dataset_intelligence_settings,
        settings,
    )
    datasets_dir = providers.Callable(
        lambda value: value.datasets_dir,
        dataset_intelligence_settings,
    )
    vector_store_path = providers.Callable(
        lambda value: value.vector_store_path,
        dataset_intelligence_settings,
    )
    knowledge_graph_path = providers.Callable(
        lambda value: value.knowledge_graph_path,
        dataset_intelligence_settings,
    )
    ioc_database_path = providers.Callable(
        lambda value: value.ioc_database_path,
        dataset_intelligence_settings,
    )
    ml_models_path = providers.Callable(
        lambda value: value.ml_models_path,
        dataset_intelligence_settings,
    )
    experiments_path = providers.Callable(
        lambda value: value.experiments_path,
        dataset_intelligence_settings,
    )
    dataset_scanner = providers.Factory(
        DatasetScanner,
        settings=dataset_intelligence_settings,
        audit_service=audit_service,
        mime_identifier=mime_identifier,
    )
    dataset_classifier = providers.Factory(DatasetClassifier)
    dataset_validator = providers.Factory(DatasetValidator)
    dataset_preprocessor = providers.Factory(DatasetPreprocessor)
    dataset_registry = providers.Factory(
        DatasetRegistry,
        dataset_repo=dataset_repo,
        scanner=dataset_scanner,
        classifier=dataset_classifier,
        validator=dataset_validator,
        preprocessor=dataset_preprocessor,
        audit_service=audit_service,
    )
    dataset_watcher = providers.Singleton(
        DatasetWatcher,
        settings=dataset_intelligence_settings,
        registry=dataset_registry,
        audit_service=audit_service,
    )


class MLContainer(containers.DeclarativeContainer):
    """ML lifecycle settings and experiment-tracking providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    dataset_registry = providers.Dependency()
    audit_service = providers.Dependency(instance_of=AuditService)

    ml_settings = providers.Callable(_ml_settings, settings)
    models_dir = providers.Callable(
        lambda value: value.models_dir,
        ml_settings,
    )
    experiments_dir = providers.Callable(
        lambda value: value.experiments_dir,
        ml_settings,
    )
    experiment_tracker = providers.Singleton(
        ExperimentTracker,
        experiments_dir=experiments_dir,
    )
    feature_extractor = providers.Singleton(ForensicFeatureExtractor)
    dataset_builder = providers.Factory(
        MLDatasetBuilder,
        feature_extractor=feature_extractor,
        dataset_registry=dataset_registry,
        settings=ml_settings,
    )
    model_registry = providers.Singleton(
        ModelRegistry,
        models_dir=models_dir,
    )
    model_trainer = providers.Factory(
        ModelTrainer,
        experiment_tracker=experiment_tracker,
        ml_settings=ml_settings,
    )
    ml_predictor = providers.Singleton(
        MLPredictor,
        model_registry=model_registry,
        feature_extractor=feature_extractor,
    )
    auto_retrainer = providers.Factory(
        AutoRetrainer,
        dataset_registry=dataset_registry,
        dataset_builder=dataset_builder,
        trainer=model_trainer,
        model_registry=model_registry,
        ml_settings=ml_settings,
        audit_service=audit_service,
    )


def _yara_rules_dir(settings: DFATSettings) -> Path:
    return Path(settings.evidence.evidence_dir).parent / "yara_rules"


def _sigma_rules_dir(settings: DFATSettings) -> Path:
    return Path(settings.evidence.evidence_dir).parent / "sigma_rules"


class ThreatIntelContainer(containers.DeclarativeContainer):
    """YARA, Sigma, MITRE, STIX, and feed-management providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    dataset_registry = providers.Dependency()
    ioc_knowledge_base = providers.Dependency()
    knowledge_graph = providers.Dependency()
    audit_service = providers.Dependency(instance_of=AuditService)

    yara_engine = providers.Singleton(
        YARAEngine,
        rules_dir=providers.Callable(_yara_rules_dir, settings),
    )
    sigma_engine = providers.Singleton(
        SigmaEngine,
        rules_dir=providers.Callable(_sigma_rules_dir, settings),
    )
    mitre_mapper = providers.Singleton(MITREMapper)
    stix_handler = providers.Singleton(STIXHandler)
    feed_manager = providers.Factory(
        ThreatFeedManager,
        dataset_registry=dataset_registry,
        ioc_kb=ioc_knowledge_base,
        yara_engine=yara_engine,
        sigma_engine=sigma_engine,
        mitre_mapper=mitre_mapper,
        stix_handler=stix_handler,
        knowledge_graph=knowledge_graph,
        audit_service=audit_service,
    )


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


def _ai_response_cache(settings: DFATSettings) -> AIResponseCache:
    """Build the AI response cache using configured TTL (default 1 hour)."""
    ai: AIEngineSettings = settings.ai_engine
    ttl = ai.cache_ttl_seconds if ai.cache_responses else 3600
    return AIResponseCache(max_size=1000, ttl_seconds=ttl)


def _enable_fallback(settings: DFATSettings) -> bool:
    """Extract fallback toggle from settings."""
    return settings.ai_engine.enable_fallback


def _use_rag(settings: DFATSettings) -> bool:
    """Extract RAG analyser toggle from settings."""
    return settings.ai_engine.use_rag


class _NullAuditService:
    """No-op audit port used when wiring AIMonitor before ServicesContainer."""

    async def log_action(self, *args: Any, **kwargs: Any) -> None:
        return None


class AIEngineContainer(containers.DeclarativeContainer):
    """AI triage engine providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)
    rag_context_builder = providers.Dependency()
    audit_service = providers.Dependency()

    llm_config = providers.Singleton(_llm_config, settings)
    ai_response_cache = providers.Singleton(_ai_response_cache, settings)
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
        cache=ai_response_cache,
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
    rag_prompts = providers.Singleton(
        RAGPromptTemplates,
        base_templates=prompts,
    )
    rag_analyzer = providers.Singleton(
        RAGEnhancedAnalyzer,
        llm_client=llm_client,
        context_builder=rag_context_builder,
        rag_prompts=rag_prompts,
        audit_service=audit_service,
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
    report_repo = providers.Dependency(instance_of=SQLAlchemyReportRepository)
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
    post_complete_hooks = providers.List()
    ml_predictor = providers.Dependency(default=None)

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
    scoring_engine = providers.Singleton(
        ScoringEngine,
        ml_predictor=ml_predictor,
    )
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
        post_complete_hooks=post_complete_hooks,
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
        enable_query_monitoring=providers.Callable(
            _database_enable_query_monitoring, settings
        ),
        slow_query_threshold_ms=providers.Callable(
            _database_slow_query_threshold_ms, settings
        ),
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


class BootstrapContainer(containers.DeclarativeContainer):
    """Bootstrap initializers and startup orchestration providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    database_engine = providers.Dependency(instance_of=DatabaseEngine)
    user_repo = providers.Dependency()
    audit_service = providers.Dependency()
    session_repo = providers.Dependency()
    parser_registry = providers.Dependency()
    dataset_registry = providers.Dependency()
    vector_store = providers.Dependency()
    embedding_engine = providers.Dependency()
    document_indexer = providers.Dependency()
    ioc_knowledge_base = providers.Dependency()
    knowledge_graph = providers.Dependency()
    llm_connection = providers.Dependency()
    rag_analyzer = providers.Dependency()
    rule_based_analyzer = providers.Dependency()
    ml_predictor = providers.Dependency()
    model_registry = providers.Dependency()
    auto_retrainer = providers.Dependency()
    feed_manager = providers.Dependency()
    yara_engine = providers.Dependency()
    sigma_engine = providers.Dependency()
    mitre_mapper = providers.Dependency()
    ground_truth_loader = providers.Dependency()
    password_hasher = providers.Dependency(instance_of=PasswordHasher)
    jwt_handler = providers.Dependency(instance_of=JWTHandler)
    ai_response_cache = providers.Dependency()

    config_validator = providers.Singleton(ConfigurationValidator)
    directory_manager = providers.Singleton(DirectoryManager)
    db_initializer = providers.Factory(
        DatabaseInitializer,
        db_engine=database_engine,
        settings=providers.Callable(_database_settings, settings),
    )
    auth_initializer = providers.Factory(
        AuthInitializer,
        user_repo=user_repo,
        password_hasher=password_hasher,
        jwt_handler=jwt_handler,
        settings=settings,
    )
    audit_initializer = providers.Factory(
        AuditInitializer,
        audit_service=audit_service,
        settings=settings,
    )
    parser_initializer = providers.Factory(
        ParserInitializer,
        parser_registry=parser_registry,
    )
    dataset_initializer = providers.Factory(
        DatasetInitializer,
        dataset_registry=dataset_registry,
        settings=settings,
    )
    knowledge_initializer = providers.Factory(
        KnowledgeInitializer,
        vector_store=vector_store,
        embedding_engine=embedding_engine,
        indexer=document_indexer,
        ioc_kb=ioc_knowledge_base,
        knowledge_graph=knowledge_graph,
        settings=settings,
    )
    ai_initializer = providers.Factory(
        AIInitializer,
        llm_connection=llm_connection,
        rag_analyzer=rag_analyzer,
        rule_based_analyzer=rule_based_analyzer,
        ml_predictor=ml_predictor,
        model_registry=model_registry,
        auto_retrainer=auto_retrainer,
        settings=settings,
    )
    threat_intel_initializer = providers.Factory(
        ThreatIntelInitializer,
        feed_manager=feed_manager,
        yara_engine=yara_engine,
        sigma_engine=sigma_engine,
        mitre_mapper=mitre_mapper,
        settings=settings,
    )
    reporting_initializer = providers.Factory(
        ReportingInitializer,
        settings=providers.Callable(_reporting_settings, settings),
    )
    evaluation_initializer = providers.Factory(
        EvaluationInitializer,
        ground_truth_loader=ground_truth_loader,
        settings=settings,
    )
    task_manager = providers.Singleton(BackgroundTaskManager)
    worker_initializer = providers.Singleton(
        WorkerInitializer,
        settings=settings,
        task_manager=task_manager,
        dataset_registry=dataset_registry,
        auto_retrainer=auto_retrainer,
        llm_connection=llm_connection,
        db_engine=database_engine,
        session_repo=session_repo,
        ai_response_cache=ai_response_cache,
    )
    boot_sequencer = providers.Factory(
        BootSequencer,
        settings=settings,
        config_validator=config_validator,
        directory_manager=directory_manager,
        db_initializer=db_initializer,
        auth_initializer=auth_initializer,
        audit_initializer=audit_initializer,
        parser_initializer=parser_initializer,
        dataset_initializer=dataset_initializer,
        knowledge_initializer=knowledge_initializer,
        ai_initializer=ai_initializer,
        threat_intel_initializer=threat_intel_initializer,
        reporting_initializer=reporting_initializer,
        evaluation_initializer=evaluation_initializer,
        worker_initializer=worker_initializer,
    )


class RuntimeContainer(containers.DeclarativeContainer):
    """Runtime health monitoring and resource tracking providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    database_engine = providers.Dependency(instance_of=DatabaseEngine)
    llm_connection = providers.Dependency()
    vector_store = providers.Dependency()
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)
    audit_service = providers.Dependency(instance_of=AuditService)
    job_manager = providers.Dependency(instance_of=JobManager)
    task_manager = providers.Dependency(instance_of=BackgroundTaskManager)
    boot_sequencer = providers.Dependency()

    service_monitor = providers.Singleton(
        ServiceMonitor,
        db_engine=database_engine,
        llm_connection=llm_connection,
        vector_store=vector_store,
        settings=settings,
        audit_logger=audit_logger,
        check_interval_seconds=30,
    )
    resource_tracker = providers.Singleton(
        ResourceTracker,
        settings=settings,
        database_engine=database_engine,
        vector_store=vector_store,
        job_manager=job_manager,
        task_manager=task_manager,
        data_dir=providers.Object(Path("data")),
    )
    recovery_manager = providers.Singleton(
        RecoveryManager,
        service_monitor=service_monitor,
        boot_sequencer=boot_sequencer,
        audit_service=audit_service,
    )
    shutdown_handler = providers.Factory(
        ShutdownHandler,
        task_manager=task_manager,
        db_engine=database_engine,
        audit_service=audit_service,
        job_manager=job_manager,
        task_stop_timeout_seconds=10.0,
        pipeline_wait_timeout_seconds=60.0,
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """Root application DI container with nested engine sub-containers."""

    config = providers.Configuration()
    settings = providers.Singleton(load_settings)
    metrics_collector = providers.Singleton(MetricsCollector)

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
        report_repo=repositories.report_repo,
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
    knowledge = providers.Container(
        KnowledgeContainer,
        settings=settings,
        audit_service=services.audit_service,
        dataset_repo=repositories.dataset_repo,
    )
    dataset_intelligence = providers.Container(
        DatasetIntelligenceContainer,
        settings=settings,
        audit_service=services.audit_service,
        mime_identifier=services.mime_identifier,
        dataset_repo=repositories.dataset_repo,
    )
    ml = providers.Container(
        MLContainer,
        settings=settings,
        dataset_registry=dataset_intelligence.dataset_registry,
        audit_service=services.audit_service,
    )
    threat_intel = providers.Container(
        ThreatIntelContainer,
        settings=settings,
        dataset_registry=dataset_intelligence.dataset_registry,
        ioc_knowledge_base=knowledge.ioc_knowledge_base,
        knowledge_graph=knowledge.knowledge_graph,
        audit_service=services.audit_service,
    )
    bootstrap = providers.Container(
        BootstrapContainer,
        settings=settings,
        database_engine=database.database_engine,
        user_repo=repositories.user_repo,
        audit_service=services.audit_service,
        session_repo=repositories.session_repo,
        parser_registry=pipeline.parser_registry,
        dataset_registry=dataset_intelligence.dataset_registry,
        vector_store=knowledge.vector_store,
        embedding_engine=knowledge.embedding_engine,
        document_indexer=knowledge.document_indexer,
        ioc_knowledge_base=knowledge.ioc_knowledge_base,
        knowledge_graph=knowledge.knowledge_graph,
        llm_connection=ai_engine.connection_manager,
        rag_analyzer=ai_engine.rag_analyzer,
        rule_based_analyzer=ai_engine.fallback,
        ml_predictor=ml.ml_predictor,
        model_registry=ml.model_registry,
        auto_retrainer=ml.auto_retrainer,
        feed_manager=threat_intel.feed_manager,
        yara_engine=threat_intel.yara_engine,
        sigma_engine=threat_intel.sigma_engine,
        mitre_mapper=threat_intel.mitre_mapper,
        ground_truth_loader=evaluation_engine.ground_truth_loader,
        password_hasher=auth.password_hasher,
        jwt_handler=auth.jwt_handler,
        ai_response_cache=ai_engine.ai_response_cache,
    )
    boot_sequencer = bootstrap.boot_sequencer
    task_manager = bootstrap.task_manager
    runtime = providers.Container(
        RuntimeContainer,
        settings=settings,
        database_engine=database.database_engine,
        llm_connection=ai_engine.connection_manager,
        vector_store=knowledge.vector_store,
        audit_logger=logging.forensic_audit_logger,
        audit_service=services.audit_service,
        job_manager=pipeline.job_manager,
        task_manager=task_manager,
        boot_sequencer=boot_sequencer,
    )
    service_monitor = runtime.service_monitor
    resource_tracker = runtime.resource_tracker
    recovery_manager = runtime.recovery_manager
    shutdown_handler = runtime.shutdown_handler


def build_application_container() -> ApplicationContainer:
    """Create the root DI container with cross-container dependencies wired.

    ``AcquisitionStage`` needs evidence-management / custody services that live
    in ``ServicesContainer``, while services need ``pipeline_orchestrator``.
    Overrides break that cycle after both nested containers exist.

    ``RAGEnhancedAnalyzer`` depends on knowledge-layer context building and
    services-layer audit. Those are wired here so ``LocalLLMClient`` remains
    independently available on ``ai_engine.llm_client``.
    """
    container = ApplicationContainer()
    container.pipeline.evidence_management_service.override(
        container.services.evidence_management_service
    )
    container.pipeline.custody_service.override(
        container.services.chain_of_custody_service
    )
    container.ai_engine.rag_context_builder.override(
        container.knowledge.rag_context_builder
    )
    container.ai_engine.audit_service.override(container.services.audit_service)
    container.pipeline.post_complete_hooks.override(
        providers.List(container.knowledge.pipeline_knowledge_hooks)
    )
    container.pipeline.ml_predictor.override(container.ml.ml_predictor)
    if _use_rag(container.settings()):
        container.pipeline.llm_analyzer.override(container.ai_engine.rag_analyzer)
    return container
