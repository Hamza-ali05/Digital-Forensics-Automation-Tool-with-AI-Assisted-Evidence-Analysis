"""Bootstrap domain models for initialization status and startup reporting."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InitPhase(str, Enum):
    """Ordered initialization phases for DFAT startup."""

    CONFIGURATION = "configuration"
    DIRECTORIES = "directories"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    AUDIT_LOGGING = "audit_logging"
    DATASET_DISCOVERY = "dataset_discovery"
    KNOWLEDGE_BASE = "knowledge_base"
    IOC_DATABASE = "ioc_database"
    THREAT_INTELLIGENCE = "threat_intelligence"
    ML_MODELS = "ml_models"
    LLM_SERVICE = "llm_service"
    RAG_PIPELINE = "rag_pipeline"
    FORENSIC_PARSERS = "forensic_parsers"
    REPORTING = "reporting"
    EVALUATION = "evaluation"
    BACKGROUND_WORKERS = "background_workers"


class InitStatus(str, Enum):
    """Outcome of a single initialization phase."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"


class SystemReadiness(str, Enum):
    """Overall system readiness after (or during) bootstrap."""

    INITIALIZING = "initializing"
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    SHUTTING_DOWN = "shutting_down"


class PhaseResult(BaseModel):
    """Result of one bootstrap initialization phase."""

    model_config = ConfigDict(validate_assignment=True)

    phase: InitPhase
    status: InitStatus
    duration_ms: float
    message: str
    details: dict = Field(default_factory=dict)
    error: Optional[str] = None
    is_critical: bool
    degraded_capabilities: list[str] = Field(default_factory=list)


class StartupReport(BaseModel):
    """Aggregate diagnostics produced by a full bootstrap run."""

    model_config = ConfigDict(validate_assignment=True)

    system_status: SystemReadiness
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_duration_ms: float = 0.0
    phases: list[PhaseResult] = Field(default_factory=list)
    critical_failures: list[str] = Field(default_factory=list)
    degraded_services: list[str] = Field(default_factory=list)
    available_capabilities: list[str] = Field(default_factory=list)
    version: str
    environment: str
    hostname: str


class ServiceHealth(BaseModel):
    """Runtime health snapshot for a named service."""

    model_config = ConfigDict(validate_assignment=True)

    service_name: str
    is_healthy: bool
    last_checked: datetime = Field(default_factory=lambda: datetime.now(UTC))
    response_time_ms: Optional[float] = None
    details: dict = Field(default_factory=dict)
    consecutive_failures: int = 0
