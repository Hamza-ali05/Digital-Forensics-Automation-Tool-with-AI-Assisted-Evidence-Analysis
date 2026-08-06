"""Dependency injection container for DFAT application wiring."""

from __future__ import annotations

from pathlib import Path

from dependency_injector import containers, providers

from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.client import LocalLLMClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.selector import select_analyzer
from dfat.ai_engine.triage.classifier import ArtefactClassifier
from dfat.ai_engine.triage.ranker import RelevanceRanker
from dfat.ai_engine.triage.summarizer import InvestigativeSummarizer
from dfat.core.enums import HashAlgorithm
from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
from dfat.forensic_engine.acquisition.integrity import IntegrityChecker
from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
from dfat.forensic_engine.normalizer import ArtefactNormalizer
from dfat.forensic_engine.orchestrator import ForensicOrchestrator
from dfat.forensic_engine.parsers.browser import BrowserHistoryParser
from dfat.forensic_engine.parsers.eventlog import EventLogParser
from dfat.forensic_engine.parsers.filesystem import FileSystemParser
from dfat.forensic_engine.parsers.memory.injection import CodeInjectionParser
from dfat.forensic_engine.parsers.memory.network import NetworkArtefactParser
from dfat.forensic_engine.parsers.memory.process import ProcessListParser
from dfat.forensic_engine.parsers.registry import RegistryParser
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument
from dfat.evaluation.usability.response_analyzer import ResponseAnalyzer
from dfat.infrastructure.cache.artefact_cache import InMemoryArtefactCache
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger, setup_logging
from dfat.infrastructure.repositories.artefact_repo import JSONArtefactRepository
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
from dfat.infrastructure.storage.local_storage import LocalFileStorage
from dfat.infrastructure.storage.secure_storage import SecureStorage
from dfat.pipeline import PipelineOrchestrator
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.settings import AIEngineSettings, DFATSettings, LoggingSettings, load_settings


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
    """Persistence repository providers."""

    local_storage = providers.Dependency(instance_of=LocalFileStorage)
    secure_storage = providers.Dependency(instance_of=SecureStorage)

    evidence_repo = providers.Singleton(
        FileSystemEvidenceRepository,
        storage=local_storage,
    )
    artefact_repo = providers.Singleton(
        JSONArtefactRepository,
        storage=local_storage,
    )
    report_repo = providers.Singleton(
        FileSystemReportRepository,
        storage=secure_storage,
    )


def _volatility_symbols_path(settings: DFATSettings) -> Path | None:
    """Extract optional Volatility symbols path from settings."""
    return settings.forensic_engine.volatility_symbols_path


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
    image_handler = providers.Singleton(
        DiskImageHandler,
        integrity_checker=integrity_checker,
        audit_logger=audit_logger,
        storage=local_storage,
    )
    memory_handler = providers.Singleton(
        MemoryDumpHandler,
        integrity_checker=integrity_checker,
        audit_logger=audit_logger,
        storage=local_storage,
        volatility_symbols_path=providers.Callable(_volatility_symbols_path, settings),
    )
    filesystem_parser = providers.Singleton(
        FileSystemParser,
        audit_logger=audit_logger,
    )
    registry_parser = providers.Singleton(
        RegistryParser,
        audit_logger=audit_logger,
    )
    browser_parser = providers.Singleton(
        BrowserHistoryParser,
        audit_logger=audit_logger,
    )
    eventlog_parser = providers.Singleton(
        EventLogParser,
        audit_logger=audit_logger,
    )
    process_parser = providers.Singleton(
        ProcessListParser,
        audit_logger=audit_logger,
    )
    network_parser = providers.Singleton(
        NetworkArtefactParser,
        audit_logger=audit_logger,
    )
    injection_parser = providers.Singleton(
        CodeInjectionParser,
        audit_logger=audit_logger,
    )
    normalizer = providers.Singleton(ArtefactNormalizer)
    parsers = providers.List(
        filesystem_parser,
        registry_parser,
        browser_parser,
        eventlog_parser,
        process_parser,
        network_parser,
        injection_parser,
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


def _llm_config(settings: DFATSettings) -> LLMConfig:
    """Build ``LLMConfig`` from application settings."""
    ai: AIEngineSettings = settings.ai_engine
    return LLMConfig(
        api_url=ai.llm_api_url,
        model=ai.llm_model,
        temperature=ai.temperature,
        max_tokens=ai.max_tokens,
        request_timeout_seconds=ai.request_timeout_seconds,
    )


def _enable_fallback(settings: DFATSettings) -> bool:
    """Extract fallback toggle from settings."""
    return settings.ai_engine.enable_fallback


class AIEngineContainer(containers.DeclarativeContainer):
    """AI triage engine providers."""

    settings = providers.Dependency(instance_of=DFATSettings)
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)

    llm_config = providers.Singleton(_llm_config, settings)
    prompts = providers.Singleton(ForensicPromptTemplates)
    llm_client = providers.Singleton(
        LocalLLMClient,
        config=llm_config,
        audit_logger=audit_logger,
        prompts=prompts,
    )
    fallback = providers.Singleton(RuleBasedAnalyzer)
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


def _report_schema_path(settings: DFATSettings) -> Path:
    """Resolve the JSON report schema path."""
    configured = Path(settings.reporting.template_dir) / "report_schema.json"
    if configured.exists():
        return configured
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

    json_exporter = providers.Singleton(
        StructuredJSONExporter,
        schema_path=providers.Callable(_report_schema_path, settings),
        hash_algorithm=providers.Callable(_primary_hash, settings),
    )
    narrative_assembler = providers.Singleton(
        NarrativeAssembler,
        template_dir=providers.Callable(_template_dir, settings),
    )
    report_builder = providers.Singleton(
        DualOutputReportBuilder,
        json_exporter=json_exporter,
        narrative_assembler=narrative_assembler,
        report_repo=report_repo,
        audit_logger=audit_logger,
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

    ground_truth_loader = providers.Singleton(
        GroundTruthLoader,
        ground_truth_dir=providers.Callable(_ground_truth_dir, settings),
    )
    metrics_calculator = providers.Singleton(MetricsCalculator)
    comparator = providers.Singleton(
        BenchmarkComparator,
        metrics_calculator=metrics_calculator,
        audit_logger=audit_logger,
        thresholds=providers.Callable(_metric_thresholds, settings),
    )
    questionnaire_model = providers.Singleton(QuestionnaireInstrument)
    response_analyzer = providers.Factory(ResponseAnalyzer)


class PipelineContainer(containers.DeclarativeContainer):
    """Top-level pipeline orchestration providers."""

    forensic_orchestrator = providers.Dependency(instance_of=ForensicOrchestrator)
    analyzer = providers.Dependency()
    fallback_analyzer = providers.Dependency(instance_of=RuleBasedAnalyzer)
    report_builder = providers.Dependency(instance_of=DualOutputReportBuilder)
    evidence_repo = providers.Dependency(instance_of=FileSystemEvidenceRepository)
    report_repo = providers.Dependency(instance_of=FileSystemReportRepository)
    ground_truth_loader = providers.Dependency(instance_of=GroundTruthLoader)
    benchmark_comparator = providers.Dependency(instance_of=BenchmarkComparator)
    audit_logger = providers.Dependency(instance_of=ForensicAuditLogger)

    pipeline_orchestrator = providers.Singleton(
        PipelineOrchestrator,
        forensic_orchestrator=forensic_orchestrator,
        analyzer=analyzer,
        fallback_analyzer=fallback_analyzer,
        report_builder=report_builder,
        evidence_repo=evidence_repo,
        report_repo=report_repo,
        ground_truth_loader=ground_truth_loader,
        benchmark_comparator=benchmark_comparator,
        audit_logger=audit_logger,
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """Root application DI container with nested engine sub-containers."""

    config = providers.Configuration()
    settings = providers.Singleton(load_settings)

    logging = providers.Container(LoggingContainer, settings=settings)
    storage = providers.Container(StorageContainer, settings=settings)
    repositories = providers.Container(
        RepositoryContainer,
        local_storage=storage.local_storage,
        secure_storage=storage.secure_storage,
    )
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
    )
    evaluation_engine = providers.Container(
        EvaluationEngineContainer,
        settings=settings,
        audit_logger=logging.forensic_audit_logger,
    )
    pipeline = providers.Container(
        PipelineContainer,
        forensic_orchestrator=forensic_engine.orchestrator,
        analyzer=ai_engine.active_analyzer,
        fallback_analyzer=ai_engine.fallback,
        report_builder=reporting_engine.report_builder,
        evidence_repo=repositories.evidence_repo,
        report_repo=repositories.report_repo,
        ground_truth_loader=evaluation_engine.ground_truth_loader,
        benchmark_comparator=evaluation_engine.comparator,
        audit_logger=logging.forensic_audit_logger,
    )
