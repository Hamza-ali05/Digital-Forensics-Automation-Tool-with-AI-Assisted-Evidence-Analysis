"""Ollama connection management, health checks, and local-URL guard.

The LLM must run locally (localhost / 127.0.0.1 / 0.0.0.0). External hosts
are rejected to satisfy GDPR and chain-of-custody constraints.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.llm.config import LLMConfig
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


class LLMHealthStatus(BaseModel):
    """Result of an Ollama health probe."""

    model_config = ConfigDict(frozen=False)

    is_healthy: bool
    model_loaded: bool
    model_name: str
    response_time_ms: float
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: Optional[str] = None


class LLMConnectionManager:
    """Manage connectivity to the local Ollama API."""

    def __init__(
        self,
        config: LLMConfig,
        audit_logger: ForensicAuditLogger,
    ) -> None:
        """Initialise the connection manager.

        Args:
            config: Local LLM configuration.
            audit_logger: Forensic audit logger (metadata only).

        Raises:
            ValueError: If ``config.api_url`` is not a local host.
        """
        self._config = config
        self._audit_logger = audit_logger
        self._is_local_url(config.api_url)

    def _is_local_url(self, url: str) -> bool:
        """Validate that ``url`` targets a local Ollama host only.

        Args:
            url: Candidate API URL.

        Returns:
            ``True`` when the host is local.

        Raises:
            ValueError: If the host is external or unparseable.
        """
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host in _LOCAL_HOSTS:
            return True
        raise ValueError(
            f"Non-local LLM endpoint forbidden for chain-of-custody: {url}"
        )

    async def check_health(self) -> LLMHealthStatus:
        """Probe Ollama via ``GET /api/tags``; never raises.

        Returns:
            Health status including whether the configured model is listed.
        """
        started = time.perf_counter()
        checked_at = datetime.now(UTC)
        try:
            self._is_local_url(self._config.api_url)
            data = await self._request_with_retry(
                method="GET",
                url=self._config.tags_url,
                timeout=self._config.health_check_timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            models = self._extract_model_names(data)
            model_loaded = self._config.model in models or any(
                name.startswith(f"{self._config.model}:") for name in models
            )
            return LLMHealthStatus(
                is_healthy=True,
                model_loaded=model_loaded,
                model_name=self._config.model,
                response_time_ms=round(elapsed_ms, 2),
                checked_at=checked_at,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 — health never raises
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.debug("Ollama health check failed: %s", exc)
            message = str(exc).strip() or type(exc).__name__
            return LLMHealthStatus(
                is_healthy=False,
                model_loaded=False,
                model_name=self._config.model,
                response_time_ms=round(elapsed_ms, 2),
                checked_at=checked_at,
                error=message,
            )

    async def verify_model_available(self) -> bool:
        """Return whether the configured model appears in Ollama's model list."""
        status = await self.check_health()
        return bool(status.is_healthy and status.model_loaded)

    async def get_model_info(self) -> Optional[dict[str, Any]]:
        """Return Ollama ``/api/show`` metadata for the configured model.

        Returns:
            Model metadata dict, or ``None`` when unavailable.
        """
        try:
            self._is_local_url(self._config.api_url)
            data = await self._request_with_retry(
                method="POST",
                url=self._config.show_url,
                timeout=self._config.health_check_timeout_seconds,
                json_body={"name": self._config.model},
            )
            if not isinstance(data, dict):
                return None
            details = data.get("details") if isinstance(data.get("details"), dict) else {}
            model_info = (
                data.get("model_info") if isinstance(data.get("model_info"), dict) else {}
            )
            return {
                "name": self._config.model,
                "model": data.get("model", self._config.model),
                "parameter_count": details.get("parameter_size"),
                "quantization": details.get("quantization_level"),
                "family": details.get("family"),
                "context_length": model_info.get(
                    "llama.context_length",
                    self._config.context_window,
                ),
                "raw": {
                    "details": details,
                    "parameters": data.get("parameters"),
                },
            }
        except Exception as exc:  # noqa: BLE001 — optional metadata
            logger.debug("Ollama model info unavailable: %s", exc)
            return None

    async def _request_with_retry(
        self,
        *,
        method: str,
        url: str,
        timeout: float,
        json_body: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Perform an HTTP request with exponential backoff retries.

        Args:
            method: HTTP method.
            url: Absolute local URL.
            timeout: Per-attempt timeout in seconds.
            json_body: Optional JSON body for POST requests.

        Returns:
            Parsed JSON response body.

        Raises:
            httpx.HTTPError: When all retry attempts fail.
        """
        attempts = max(1, self._config.max_retries)
        delay = max(0.0, self._config.retry_delay_seconds)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(
                        method,
                        url,
                        json=json_body,
                    )
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:  # noqa: BLE001 — retry then raise
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                backoff = delay * (2**attempt)
                logger.debug(
                    "Ollama request failed (attempt %s/%s): %s; retry in %.1fs",
                    attempt + 1,
                    attempts,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

        assert last_error is not None
        raise last_error

    @staticmethod
    def _extract_model_names(payload: Any) -> list[str]:
        """Extract model names from an Ollama ``/api/tags`` response."""
        if not isinstance(payload, dict):
            return []
        models = payload.get("models")
        if not isinstance(models, list):
            return []
        names: list[str] = []
        for item in models:
            if isinstance(item, dict):
                name = item.get("name") or item.get("model")
                if isinstance(name, str) and name:
                    names.append(name)
        return names
