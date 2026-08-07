"""Hierarchical configuration management for DFAT."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from dfat.core.enums import HashAlgorithm

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_DIR = _PROJECT_ROOT / "config"


class EvidenceSettings(BaseModel):
    """Evidence path and supported format settings."""

    evidence_dir: Path = Path("./data/evidence")
    supported_disk_formats: set[str] = Field(
        default_factory=lambda: {".dd", ".raw", ".e01", ".img", ".001"}
    )
    supported_memory_formats: set[str] = Field(
        default_factory=lambda: {".raw", ".vmem", ".dmp", ".mem"}
    )
    max_evidence_size_gb: float = 100.0


class ForensicEngineSettings(BaseModel):
    """Forensic acquisition and parsing engine settings."""

    volatility_symbols_path: Optional[Path] = None
    max_artefacts_per_category: int = 10000
    parse_timeout_seconds: int = 300


class AIEngineSettings(BaseModel):
    """Local LLaMA-3 AI triage engine settings."""

    llm_api_url: str = "http://localhost:11434/api/generate"
    llm_model: str = "llama3"
    temperature: float = 0.1
    max_tokens: int = 4096
    request_timeout_seconds: int = 120
    enable_fallback: bool = True
    context_window: int = 8192
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    cache_responses: bool = True
    cache_ttl_seconds: int = 3600
    max_input_artefacts: int = 500


class ReportingSettings(BaseModel):
    """Dual-output reporting engine settings."""

    output_dir: Path = Path("./data/outputs")
    json_schema_version: str = "1.0.0"
    template_dir: Path = Path("src/dfat/reporting/templates")


class EvaluationSettings(BaseModel):
    """Benchmark evaluation dataset settings."""

    ground_truth_dir: Path = Path("./data/ground_truth")
    dfrws_dataset_path: Optional[Path] = None
    cfreds_dataset_path: Optional[Path] = None
    metrics_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "precision_min": 0.0,
            "recall_min": 0.0,
            "f1_min": 0.0,
        }
    )


class LoggingSettings(BaseModel):
    """Application logging and forensic audit trail settings."""

    log_level: str = "INFO"
    audit_log_path: Path = Path("./data/outputs/audit.log")
    log_format: str = "json"


class SecuritySettings(BaseModel):
    """Integrity hashing and security settings."""

    hash_algorithms: list[HashAlgorithm] = Field(
        default_factory=lambda: [HashAlgorithm.SHA256, HashAlgorithm.MD5]
    )
    primary_hash: HashAlgorithm = HashAlgorithm.SHA256


class DatabaseSettings(BaseModel):
    """Async SQLAlchemy database settings.

    The database stores metadata, audit trails, users, and analysis results.
    Raw forensic evidence files are never persisted here.
    """

    url: str = "sqlite+aiosqlite:///./data/dfat.db"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    create_tables_on_startup: bool = True


class AuthSettings(BaseModel):
    """Local JWT authentication and account lockout settings."""

    secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    password_min_length: int = 12
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30


class ApiSettings(BaseModel):
    """HTTP API surface settings (CORS, etc.)."""

    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )


class PipelineSettings(BaseModel):
    """Five-stage forensic pipeline orchestration settings."""

    max_concurrent_jobs: int = 1
    stage_timeout_seconds: int = 600
    parser_timeout_seconds: int = 300
    max_artefacts_per_category: int = 10000
    enable_artefact_correlation: bool = True
    enable_timeline_generation: bool = True
    enable_ioc_detection: bool = True
    volatility_plugins_timeout: int = 300
    enable_memory_registry: bool = True


class DFATSettings(BaseSettings):
    """Top-level DFAT settings composed from YAML and environment variables.

    Precedence: ``default.yaml`` → ``{env}.yaml`` → environment variables.
    Nested environment keys use ``DFAT_`` prefix and ``__`` delimiter
    (e.g., ``DFAT_AI_ENGINE__LLM_MODEL``).
    """

    model_config = SettingsConfigDict(
        env_prefix="DFAT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    evidence: EvidenceSettings = Field(default_factory=EvidenceSettings)
    forensic_engine: ForensicEngineSettings = Field(default_factory=ForensicEngineSettings)
    ai_engine: AIEngineSettings = Field(default_factory=AIEngineSettings)
    reporting: ReportingSettings = Field(default_factory=ReportingSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a YAML file into a dictionary.

    Args:
        path: Path to a YAML configuration file.

    Returns:
        Parsed mapping, or an empty dict when the file is missing/empty.
    """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` onto ``base`` without mutating inputs.

    Args:
        base: Base configuration mapping.
        overlay: Overlay mapping whose values take precedence.

    Returns:
        Merged configuration mapping.
    """
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(
    env: Optional[str] = None,
    config_dir: Optional[Path] = None,
) -> DFATSettings:
    """Load hierarchical settings from YAML and environment variables.

    Args:
        env: Environment name (``development``, ``testing``, ``production``).
            Defaults to ``DFAT_ENV`` or ``development``.
        config_dir: Optional configuration directory override.

    Returns:
        Fully resolved ``DFATSettings`` instance.
    """
    env_name = env or os.getenv("DFAT_ENV", "development")
    directory = config_dir or _DEFAULT_CONFIG_DIR

    data = _load_yaml_file(directory / "default.yaml")
    data = _deep_merge(data, _load_yaml_file(directory / f"{env_name}.yaml"))
    data["env"] = env_name

    # YAML provides base values; BaseSettings applies DFAT_* env overrides.
    return DFATSettings(**data)
