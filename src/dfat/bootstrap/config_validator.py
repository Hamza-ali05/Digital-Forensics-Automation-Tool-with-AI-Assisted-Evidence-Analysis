"""Configuration validation as the first critical bootstrap phase."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)

_VALID_ENVIRONMENTS = frozenset({"development", "testing", "production"})
_JWT_PLACEHOLDERS = frozenset(
    {
        "CHANGE-ME-IN-PRODUCTION",
        "CHANGE-ME-IN-PRODUCTION-USE-SECRETS",
    }
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})  # nosec B104
_DB_SCHEMES = frozenset(
    {
        "sqlite",
        "sqlite+aiosqlite",
        "postgresql",
        "postgresql+asyncpg",
        "postgres",
        "postgres+asyncpg",
    }
)
_MIN_JWT_LENGTH = 32
_MIN_TOKEN_EXPIRE_MINUTES = 5
_MAX_TOKEN_EXPIRE_MINUTES = 24 * 60  # exclusive upper bound (< 24 hours)


class ConfigurationValidator:
    """Validates every configuration setting before any subsystem starts.

    Runs as the FIRST initialization phase. Failure here aborts startup.
    """

    async def validate(self, settings: DFATSettings) -> PhaseResult:
        """Run all configuration checks and return a phase result.

        Args:
            settings: Fully loaded ``DFATSettings`` instance.

        Returns:
            ``PhaseResult`` with ``COMPLETED`` or ``FAILED``.
        """
        started = time.perf_counter()
        checks: list[dict[str, Any]] = []
        failures: list[str] = []

        def _record(name: str, ok: bool, message: str) -> None:
            checks.append({"check": name, "passed": ok, "message": message})
            if ok:
                logger.info("Config check PASS [%s]: %s", name, message)
            else:
                failures.append(f"{name}: {message}")
                logger.error("Config check FAIL [%s]: %s", name, message)

        env = (settings.env or "").strip().lower()
        _record(
            "dfat_env",
            env in _VALID_ENVIRONMENTS,
            (
                f"DFAT_ENV={settings.env!r} is valid"
                if env in _VALID_ENVIRONMENTS
                else (
                    f"DFAT_ENV={settings.env!r} is invalid. "
                    f"Set DFAT_ENV to one of: {', '.join(sorted(_VALID_ENVIRONMENTS))}."
                )
            ),
        )

        secret = (settings.auth.secret_key or "").strip()
        if self._is_production(env):
            is_placeholder = secret in _JWT_PLACEHOLDERS or secret.startswith(
                "CHANGE-ME"
            )
            _record(
                "jwt_secret_placeholder",
                not is_placeholder,
                (
                    "JWT secret is not a default placeholder"
                    if not is_placeholder
                    else (
                        "JWT secret key must not use the default placeholder in "
                        "production. Set DFAT_AUTH__SECRET_KEY to a strong random "
                        "value (e.g. via scripts/generate_secrets.sh)."
                    )
                ),
            )

        jwt_ok = len(secret) >= _MIN_JWT_LENGTH
        _record(
            "jwt_secret_length",
            jwt_ok,
            (
                f"JWT secret length is {len(secret)} (>= {_MIN_JWT_LENGTH})"
                if jwt_ok
                else (
                    f"JWT secret key is {len(secret)} characters; require >= "
                    f"{_MIN_JWT_LENGTH}. Generate a longer secret and set "
                    "DFAT_AUTH__SECRET_KEY."
                )
            ),
        )

        db_ok, db_msg = self._validate_database_url(settings.database.url)
        _record("database_url", db_ok, db_msg)

        evidence_ok, evidence_msg = self._validate_path_config(
            Path(settings.evidence.evidence_dir),
            must_exist=False,
        )
        _record(
            "evidence_dir",
            evidence_ok and bool(str(settings.evidence.evidence_dir).strip()),
            (
                f"Evidence directory configured: {settings.evidence.evidence_dir}"
                if evidence_ok and str(settings.evidence.evidence_dir).strip()
                else (
                    "Evidence directory path is not configured. Set "
                    "DFAT_EVIDENCE__EVIDENCE_DIR or evidence.evidence_dir in YAML."
                )
            ),
        )

        output_ok, _ = self._validate_path_config(
            Path(settings.reporting.output_dir),
            must_exist=False,
        )
        _record(
            "output_dir",
            output_ok and bool(str(settings.reporting.output_dir).strip()),
            (
                f"Output directory configured: {settings.reporting.output_dir}"
                if output_ok and str(settings.reporting.output_dir).strip()
                else (
                    "Output directory path is not configured. Set "
                    "DFAT_REPORTING__OUTPUT_DIR or reporting.output_dir in YAML."
                )
            ),
        )

        audit_ok, _ = self._validate_path_config(
            Path(settings.logging.audit_log_path),
            must_exist=False,
        )
        _record(
            "audit_log_path",
            audit_ok and bool(str(settings.logging.audit_log_path).strip()),
            (
                f"Audit log path configured: {settings.logging.audit_log_path}"
                if audit_ok and str(settings.logging.audit_log_path).strip()
                else (
                    "Audit log path is not configured. Set "
                    "DFAT_LOGGING__AUDIT_LOG_PATH or logging.audit_log_path in YAML."
                )
            ),
        )

        llm_url = (settings.ai_engine.llm_api_url or "").strip()
        try:
            local_ok = self._is_local_url(llm_url)
            llm_msg = f"LLM API URL is local: {llm_url}"
        except ValueError as exc:
            local_ok = False
            llm_msg = (
                f"{exc} Remediation: set DFAT_AI_ENGINE__LLM_API_URL to a localhost "
                "Ollama endpoint (e.g. http://localhost:11434/api/generate)."
            )
        _record("llm_api_url_local", local_ok, llm_msg)

        model_name = (settings.ai_engine.llm_model or "").strip()
        _record(
            "llm_model",
            bool(model_name),
            (
                f"LLM model configured: {model_name}"
                if model_name
                else (
                    "LLM model name is not configured. Set "
                    "DFAT_AI_ENGINE__LLM_MODEL (e.g. llama3)."
                )
            ),
        )

        if self._is_production(env):
            path_items = {
                "evidence.evidence_dir": Path(settings.evidence.evidence_dir),
                "reporting.output_dir": Path(settings.reporting.output_dir),
                "logging.audit_log_path": Path(settings.logging.audit_log_path),
            }
            relative = [
                name for name, path in path_items.items() if not path.is_absolute()
            ]
            abs_ok = not relative
            _record(
                "production_absolute_paths",
                abs_ok,
                (
                    "All configured paths are absolute in production"
                    if abs_ok
                    else (
                        "Production requires absolute paths. Relative paths found: "
                        f"{', '.join(relative)}. Update YAML or DFAT_* path env vars."
                    )
                ),
            )
        else:
            _record(
                "production_absolute_paths",
                True,
                "Absolute-path rule skipped (non-production environment)",
            )

        ports_ok, ports_msg = self._validate_ports(settings)
        _record("port_ranges", ports_ok, ports_msg)

        expire = int(settings.auth.access_token_expire_minutes)
        token_ok = _MIN_TOKEN_EXPIRE_MINUTES < expire < _MAX_TOKEN_EXPIRE_MINUTES
        _record(
            "token_expiry",
            token_ok,
            (
                f"Access token expiry is {expire} minutes (valid range)"
                if token_ok
                else (
                    f"Access token expiry is {expire} minutes; require > "
                    f"{_MIN_TOKEN_EXPIRE_MINUTES} and < {_MAX_TOKEN_EXPIRE_MINUTES} "
                    "(24 hours). Set DFAT_AUTH__ACCESS_TOKEN_EXPIRE_MINUTES."
                )
            ),
        )

        duration_ms = (time.perf_counter() - started) * 1000.0
        if failures:
            remediation = "; ".join(failures)
            return PhaseResult(
                phase=InitPhase.CONFIGURATION,
                status=InitStatus.FAILED,
                duration_ms=duration_ms,
                message="Configuration validation failed — startup aborted",
                details={"checks": checks, "failure_count": len(failures)},
                error=remediation,
                is_critical=True,
            )

        return PhaseResult(
            phase=InitPhase.CONFIGURATION,
            status=InitStatus.COMPLETED,
            duration_ms=duration_ms,
            message="Configuration validation passed",
            details={"checks": checks, "failure_count": 0},
            is_critical=True,
        )

    def _validate_database_url(self, url: str) -> tuple[bool, str]:
        """Validate database URL presence and basic syntax.

        Args:
            url: SQLAlchemy async database URL.

        Returns:
            ``(ok, message)`` pair with remediation on failure.
        """
        raw = (url or "").strip()
        if not raw:
            return (
                False,
                "Database URL is empty. Set DFAT_DATABASE__URL "
                "(e.g. sqlite+aiosqlite:///./data/dfat.db).",
            )
        if raw.startswith("${") or "${" in raw:
            return (
                False,
                f"Database URL contains unresolved placeholder: {raw!r}. "
                "Export DFAT_DATABASE__URL before starting in production.",
            )
        parsed = urlparse(raw)
        scheme = (parsed.scheme or "").lower()
        if scheme not in _DB_SCHEMES:
            return (
                False,
                f"Database URL scheme {scheme!r} is invalid. Use one of: "
                f"{', '.join(sorted(_DB_SCHEMES))}. Current value: {raw!r}.",
            )
        if scheme.startswith("sqlite"):
            # sqlite URLs may have empty netloc; path/database must be present.
            if not parsed.path and ":memory:" not in raw:
                return (
                    False,
                    f"SQLite database URL is missing a database path: {raw!r}.",
                )
            return True, f"Database URL is valid ({scheme})"
        if not parsed.hostname:
            return (
                False,
                f"Database URL is missing a host: {raw!r}. "
                "Example: postgresql+asyncpg://user:pass@localhost:5432/dfat",
            )
        return True, f"Database URL is valid ({scheme}://{parsed.hostname})"

    def _validate_path_config(
        self,
        path: Path,
        must_exist: bool,
    ) -> tuple[bool, str]:
        """Validate a configured filesystem path.

        Args:
            path: Candidate path from settings.
            must_exist: When ``True``, require the path to exist on disk.

        Returns:
            ``(ok, message)`` pair.
        """
        if path is None or not str(path).strip():
            return False, "Path is not configured"
        if must_exist and not path.exists():
            return (
                False,
                f"Path does not exist: {path}. Create it or update the setting.",
            )
        return True, f"Path configured: {path}"

    def _is_production(self, env: str) -> bool:
        """Return ``True`` when ``env`` is production."""
        return (env or "").strip().lower() == "production"

    def _is_local_url(self, url: str) -> bool:
        """Validate that ``url`` targets a local host only.

        Args:
            url: Candidate LLM API URL.

        Returns:
            ``True`` when the host is local.

        Raises:
            ValueError: If the host is external, empty, or unparseable.
        """
        if not (url or "").strip():
            raise ValueError("LLM API URL is empty.")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError(f"LLM API URL has no host: {url!r}.")
        if host in _LOCAL_HOSTS:
            return True
        raise ValueError(
            f"Non-local LLM endpoint forbidden for chain-of-custody: {url}"
        )

    def _validate_ports(self, settings: DFATSettings) -> tuple[bool, str]:
        """Validate port numbers embedded in configured URLs.

        Args:
            settings: Application settings.

        Returns:
            ``(ok, message)`` pair.
        """
        candidates: list[tuple[str, int | None]] = []

        llm_parsed = urlparse(settings.ai_engine.llm_api_url or "")
        candidates.append(("ai_engine.llm_api_url", llm_parsed.port))

        db_parsed = urlparse(settings.database.url or "")
        candidates.append(("database.url", db_parsed.port))

        for origin in settings.api.cors_allow_origins or []:
            origin_parsed = urlparse(origin)
            candidates.append((f"cors:{origin}", origin_parsed.port))

        invalid: list[str] = []
        seen: list[str] = []
        for label, port in candidates:
            if port is None:
                continue
            seen.append(f"{label}={port}")
            if not (1 <= port <= 65535):
                invalid.append(f"{label}={port}")

        if invalid:
            return (
                False,
                "Invalid port number(s) (must be 1–65535): "
                f"{', '.join(invalid)}. Correct the URL(s) in configuration.",
            )
        if seen:
            return True, f"Port numbers valid: {', '.join(seen)}"
        return True, "No explicit ports configured (defaults acceptable)"
