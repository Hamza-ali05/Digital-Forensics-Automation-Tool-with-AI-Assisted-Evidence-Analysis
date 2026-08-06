"""Dependency injection container for DFAT application wiring."""

from __future__ import annotations

from pathlib import Path

from dependency_injector import containers, providers

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
from dfat.infrastructure.cache.artefact_cache import InMemoryArtefactCache
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger, setup_logging
from dfat.infrastructure.repositories.artefact_repo import JSONArtefactRepository
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
from dfat.infrastructure.storage.local_storage import LocalFileStorage
from dfat.infrastructure.storage.secure_storage import SecureStorage
from dfat.settings import DFATSettings, LoggingSettings, load_settings


def _placeholder() -> None:
    """Return a temporary unbound dependency placeholder."""
    return None


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


class AIEngineContainer(containers.DeclarativeContainer):
    """AI triage engine providers."""

    llm_client = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    classifier = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    ranker = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    summarizer = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    fallback = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N


class ReportingEngineContainer(containers.DeclarativeContainer):
    """Dual-output reporting engine providers."""

    json_exporter = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    narrative_assembler = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    report_builder = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N


class EvaluationEngineContainer(containers.DeclarativeContainer):
    """Benchmark and usability evaluation providers."""

    ground_truth_loader = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    metrics_calculator = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    comparator = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    questionnaire_model = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N
    response_analyzer = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N


class PipelineContainer(containers.DeclarativeContainer):
    """Top-level pipeline orchestration providers."""

    pipeline_orchestrator = providers.Callable(_placeholder)
    # TODO: Wire to concrete implementation in Prompt N


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
    ai_engine = providers.Container(AIEngineContainer)
    reporting_engine = providers.Container(ReportingEngineContainer)
    evaluation_engine = providers.Container(EvaluationEngineContainer)
    pipeline = providers.Container(PipelineContainer)
