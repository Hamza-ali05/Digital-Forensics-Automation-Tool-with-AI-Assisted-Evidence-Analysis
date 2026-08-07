"""Local LLaMA-3 HTTP clients for Ollama and artefact analysis.

``OllamaClient`` is the low-level async HTTP client (Prompt 5.2).
``LegacyLocalLLMClient`` is the earlier sync HTTP ``IArtefactAnalyzer`` used by
unit tests; production wiring uses the assembled client in
``dfat.ai_engine.analyzer.LocalLLMClient``.

Known limitation: base LLaMA-3 may produce less accurate forensic summaries
than a fine-tuned variant (Sharma et al., 2025). Structured JSON reporting
(Stage 4) remains the auditable record independent of LLM narrative
(Scanlon et al., 2023).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.core.enums import PipelineStage, SuspicionLevel
from dfat.core.exceptions import LLMConnectionError, LLMResponseError, LLMTimeoutError
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "0.0.0.0", "::1"})


class LLMResponse(BaseModel):
    """Normalised response from an Ollama generate/chat call."""

    model_config = ConfigDict(frozen=False)

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_duration_ns: int = 0
    load_duration_ns: int = 0
    eval_duration_ns: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    done: bool = True


class OllamaClient:
    """Low-level HTTP client for the Ollama local LLM API.

    Handles request construction, response streaming, retries, and
    error conversion to DFAT domain exceptions.
    """

    def __init__(
        self,
        config: LLMConfig,
        connection_manager: LLMConnectionManager,
        audit_logger: ForensicAuditLogger,
    ) -> None:
        """Initialise the Ollama HTTP client.

        Args:
            config: Local LLM configuration.
            connection_manager: Connectivity / local-URL guard.
            audit_logger: Forensic audit logger (metadata only; never evidence).
        """
        connection_manager._is_local_url(config.api_url)
        self._config = config
        self._connection = connection_manager
        self._audit_logger = audit_logger

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """Generate a completion via ``POST /api/generate`` (non-streaming).

        Args:
            prompt: User / task prompt text.
            system: Optional system prompt override.
            temperature: Optional temperature override.

        Returns:
            Parsed ``LLMResponse``.

        Raises:
            LLMConnectionError: Connection failure after retries.
            LLMTimeoutError: Request timeout after retries.
            LLMResponseError: Non-success HTTP status or malformed body.
        """
        system_prompt = system if system is not None else self._config.system_prompt
        temp = self._config.temperature if temperature is None else temperature
        body = self._build_request_body(prompt, system_prompt, temp)
        body["stream"] = False
        return await self._post_with_retries(
            url=self._config.generate_url,
            body=body,
            prompt_for_estimate=prompt,
            action="OLLAMA_GENERATE",
        )

    async def generate_streaming(
        self,
        prompt: str,
        system: Optional[str] = None,
        callback: Optional[Callable[[str], None]] = None,
    ) -> LLMResponse:
        """Generate a completion with ``stream: true``, accumulating chunks.

        Args:
            prompt: User / task prompt text.
            system: Optional system prompt override.
            callback: Optional per-chunk text callback.

        Returns:
            Complete ``LLMResponse`` when the stream ends.
        """
        system_prompt = system if system is not None else self._config.system_prompt
        body = self._build_request_body(
            prompt,
            system_prompt,
            self._config.temperature,
        )
        body["stream"] = True
        return await self._stream_with_retries(
            url=self._config.generate_url,
            body=body,
            prompt_for_estimate=prompt,
            callback=callback,
            text_field="response",
            action="OLLAMA_GENERATE_STREAM",
        )

    async def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        """Run a multi-turn chat via ``POST /api/chat``.

        Args:
            messages: Ollama chat messages (``role`` / ``content``).

        Returns:
            Parsed ``LLMResponse`` from the final assistant message.
        """
        body: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self._config.temperature,
                "top_p": self._config.top_p,
                "repeat_penalty": self._config.repeat_penalty,
                "num_predict": self._config.num_predict,
            },
        }
        if self._config.stop_sequences:
            body["options"]["stop"] = list(self._config.stop_sequences)

        prompt_estimate = "\n".join(
            str(item.get("content", "")) for item in messages if isinstance(item, dict)
        )
        return await self._post_with_retries(
            url=f"{self._config.base_url}/api/chat",
            body=body,
            prompt_for_estimate=prompt_estimate,
            action="OLLAMA_CHAT",
            chat_mode=True,
        )

    def _build_request_body(
        self,
        prompt: str,
        system: str,
        temperature: float,
    ) -> dict[str, Any]:
        """Build an Ollama ``/api/generate`` request body."""
        options: dict[str, Any] = {
            "temperature": temperature,
            "top_p": self._config.top_p,
            "repeat_penalty": self._config.repeat_penalty,
            "num_predict": self._config.num_predict,
        }
        if self._config.stop_sequences:
            options["stop"] = list(self._config.stop_sequences)
        return {
            "model": self._config.model,
            "prompt": prompt,
            "system": system,
            "options": options,
        }

    def _handle_error(self, error: Exception, attempt: int) -> None:
        """Convert transport errors to DFAT exceptions (always raises).

        Args:
            error: Underlying exception from httpx or parsing.
            attempt: 1-based attempt number (for context only).

        Raises:
            LLMConnectionError: Connection / HTTP transport failures.
            LLMTimeoutError: Timeouts.
            LLMResponseError: Bad status or malformed payloads.
        """
        context = {
            "api_url": self._config.base_url,
            "attempt": attempt,
            "model": self._config.model,
        }
        if isinstance(error, httpx.TimeoutException):
            raise LLMTimeoutError(
                "Local LLM API request timed out",
                context={
                    **context,
                    "timeout_seconds": self._config.request_timeout_seconds,
                },
            ) from error
        if isinstance(error, httpx.ConnectError):
            raise LLMConnectionError(
                "Failed to connect to local LLM API",
                context=context,
            ) from error
        if isinstance(error, httpx.HTTPStatusError):
            raise LLMResponseError(
                f"Local LLM API returned HTTP {error.response.status_code}",
                context={
                    **context,
                    "status_code": error.response.status_code,
                },
            ) from error
        if isinstance(error, (LLMConnectionError, LLMTimeoutError, LLMResponseError)):
            raise error
        if isinstance(error, httpx.HTTPError):
            raise LLMConnectionError(
                f"Local LLM API HTTP error: {error}",
                context=context,
            ) from error
        if isinstance(error, (ValueError, json.JSONDecodeError, KeyError, TypeError)):
            raise LLMResponseError(
                f"Local LLM API response parse error: {error}",
                context=context,
            ) from error
        raise LLMConnectionError(
            f"Local LLM API unexpected error: {error}",
            context=context,
        ) from error

    @staticmethod
    def _compute_token_estimate(text: str) -> int:
        """Rough token estimate (``len(text) / 4``) for audit logging only."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    async def _post_with_retries(
        self,
        *,
        url: str,
        body: dict[str, Any],
        prompt_for_estimate: str,
        action: str,
        chat_mode: bool = False,
    ) -> LLMResponse:
        """POST JSON with exponential backoff retries."""
        attempts = max(1, self._config.max_retries)
        delay = max(0.0, self._config.retry_delay_seconds)
        prompt_tokens_est = self._compute_token_estimate(prompt_for_estimate)
        started = time.perf_counter()
        request_ts = datetime.now(UTC).isoformat()

        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action=f"{action}_REQUEST",
            evidence_id="n/a",
            details={
                "timestamp": request_ts,
                "model": self._config.model,
                "prompt_token_estimate": prompt_tokens_est,
                "api_host": urlparse(url).hostname,
            },
        )

        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._config.request_timeout_seconds,
                ) as client:
                    response = await client.post(url, json=body)
                    if response.status_code != 200:
                        raise httpx.HTTPStatusError(
                            f"HTTP {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    data = response.json()
                parsed = self._parse_response(
                    data,
                    prompt_estimate=prompt_tokens_est,
                    chat_mode=chat_mode,
                )
                duration_ms = (time.perf_counter() - started) * 1000.0
                self._audit_logger.log_action(
                    stage=PipelineStage.AI_TRIAGE,
                    action=f"{action}_RESPONSE",
                    evidence_id="n/a",
                    details={
                        "timestamp": datetime.now(UTC).isoformat(),
                        "model": parsed.model,
                        "prompt_tokens": parsed.prompt_tokens,
                        "completion_tokens": parsed.completion_tokens,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                return parsed
            except Exception as exc:  # noqa: BLE001 — convert / retry
                last_error = exc
                if attempt >= attempts:
                    self._handle_error(exc, attempt)
                backoff = delay * (2 ** (attempt - 1))
                logger.debug(
                    "Ollama %s failed (attempt %s/%s): %s; retry in %.1fs",
                    action,
                    attempt,
                    attempts,
                    type(exc).__name__,
                    backoff,
                )
                await asyncio.sleep(backoff)

        assert last_error is not None
        self._handle_error(last_error, attempts)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _stream_with_retries(
        self,
        *,
        url: str,
        body: dict[str, Any],
        prompt_for_estimate: str,
        callback: Optional[Callable[[str], None]],
        text_field: str,
        action: str,
    ) -> LLMResponse:
        """Stream NDJSON chunks with retries; return the accumulated response."""
        attempts = max(1, self._config.max_retries)
        delay = max(0.0, self._config.retry_delay_seconds)
        prompt_tokens_est = self._compute_token_estimate(prompt_for_estimate)
        started = time.perf_counter()
        request_ts = datetime.now(UTC).isoformat()

        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action=f"{action}_REQUEST",
            evidence_id="n/a",
            details={
                "timestamp": request_ts,
                "model": self._config.model,
                "prompt_token_estimate": prompt_tokens_est,
                "streaming": True,
                "api_host": urlparse(url).hostname,
            },
        )

        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                chunks: list[str] = []
                final_meta: dict[str, Any] = {}
                async with httpx.AsyncClient(
                    timeout=self._config.request_timeout_seconds,
                ) as client:
                    async with client.stream("POST", url, json=body) as response:
                        if response.status_code != 200:
                            await response.aread()
                            raise httpx.HTTPStatusError(
                                f"HTTP {response.status_code}",
                                request=response.request,
                                response=response,
                            )
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                payload = json.loads(line)
                            except json.JSONDecodeError as exc:
                                raise LLMResponseError(
                                    "Malformed streaming JSON chunk from Ollama",
                                    context={"chunk_preview_chars": len(line)},
                                ) from exc
                            piece = payload.get(text_field)
                            if isinstance(piece, str) and piece:
                                chunks.append(piece)
                                if callback is not None:
                                    callback(piece)
                            if payload.get("done") is True:
                                final_meta = payload
                text = "".join(chunks)
                if not final_meta:
                    final_meta = {
                        "response": text,
                        "model": self._config.model,
                        "done": True,
                    }
                else:
                    final_meta = {**final_meta, "response": text}
                parsed = self._parse_response(
                    final_meta,
                    prompt_estimate=prompt_tokens_est,
                    chat_mode=False,
                )
                duration_ms = (time.perf_counter() - started) * 1000.0
                self._audit_logger.log_action(
                    stage=PipelineStage.AI_TRIAGE,
                    action=f"{action}_RESPONSE",
                    evidence_id="n/a",
                    details={
                        "timestamp": datetime.now(UTC).isoformat(),
                        "model": parsed.model,
                        "prompt_tokens": parsed.prompt_tokens,
                        "completion_tokens": parsed.completion_tokens,
                        "duration_ms": round(duration_ms, 2),
                        "streaming": True,
                    },
                )
                return parsed
            except Exception as exc:  # noqa: BLE001 — convert / retry
                last_error = exc
                if attempt >= attempts:
                    self._handle_error(exc, attempt)
                backoff = delay * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

        assert last_error is not None
        self._handle_error(last_error, attempts)
        raise AssertionError("unreachable")  # pragma: no cover

    def _parse_response(
        self,
        data: dict[str, Any],
        *,
        prompt_estimate: int,
        chat_mode: bool,
    ) -> LLMResponse:
        """Map an Ollama JSON payload to ``LLMResponse``."""
        if chat_mode:
            message = data.get("message")
            text = ""
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    text = content
        else:
            raw = data.get("response")
            text = raw if isinstance(raw, str) else ""

        if not isinstance(text, str):
            raise LLMResponseError(
                "Local LLM API response missing text content",
                context={"keys": list(data.keys())},
            )

        prompt_tokens = self._int_field(data, "prompt_eval_count", prompt_estimate)
        completion_tokens = self._int_field(
            data,
            "eval_count",
            self._compute_token_estimate(text),
        )
        created_raw = data.get("created_at")
        created_at = datetime.now(UTC)
        if isinstance(created_raw, str):
            try:
                created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            except ValueError:
                created_at = datetime.now(UTC)

        return LLMResponse(
            text=text,
            model=str(data.get("model") or self._config.model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_duration_ns=self._int_field(data, "total_duration", 0),
            load_duration_ns=self._int_field(data, "load_duration", 0),
            eval_duration_ns=self._int_field(data, "eval_duration", 0),
            created_at=created_at,
            done=bool(data.get("done", True)),
        )

    @staticmethod
    def _int_field(data: dict[str, Any], key: str, default: int) -> int:
        """Coerce a numeric Ollama field to ``int``."""
        value = data.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


class LegacyLocalLLMClient(IArtefactAnalyzer):
    """Legacy sync HTTP LLaMA-3 client for artefact triage and summarisation.

    Prefer ``dfat.ai_engine.analyzer.LocalLLMClient`` for the full Prompt 5
    pipeline (classify → validate → rank → summarize → monitor).
    """

    def __init__(
        self,
        config: LLMConfig,
        audit_logger: ForensicAuditLogger,
        prompts: Optional[ForensicPromptTemplates] = None,
        ollama_client: Optional[OllamaClient] = None,
    ) -> None:
        """Initialise the local LLM analyser client.

        Args:
            config: Local API configuration.
            audit_logger: Forensic audit logger (metadata only; no evidence body).
            prompts: Optional prompt template manager.
            ollama_client: Optional low-level Ollama client for generate calls.
        """
        self._assert_local_endpoint(config.api_url)
        self._config = config
        self._audit_logger = audit_logger
        self._prompts = prompts or ForensicPromptTemplates()
        self._ollama = ollama_client

    @property
    def analyzer_name(self) -> str:
        """Return the stable analyser identifier."""
        return "LocalLLaMA3Client"

    def is_available(self) -> bool:
        """Return True when the local LLM API responds successfully.

        Returns:
            True if a health-check request returns HTTP 200 within 5 seconds.
        """
        health_url = self._health_url()
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(health_url)
            return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    def analyze(self, artefact_set: ArtefactSet) -> list[RankedArtefact]:
        """Classify and rank artefacts via the local LLM.

        Args:
            artefact_set: Parsed artefacts pending triage.

        Returns:
            Ranked artefacts with suspicion levels and scores.
        """
        artefacts = list(artefact_set.artefacts)
        if not artefacts:
            return []

        classification_prompt = self._prompts.render(
            "classification",
            artefacts=[a.model_dump(mode="json") for a in artefacts],
        )
        classification_text = self._call_llm(classification_prompt)
        ranked = self._parse_classification_response(classification_text, artefacts)

        ranking_prompt = self._prompts.render(
            "ranking",
            artefacts=[r.model_dump(mode="json") for r in ranked],
        )
        ranking_text = self._call_llm(ranking_prompt)
        return self._apply_ranking_response(ranking_text, ranked)

    def summarize(self, ranked_artefacts: list[RankedArtefact]) -> str:
        """Generate an investigative narrative summary via the local LLM.

        Args:
            ranked_artefacts: Triaged artefacts to summarise.

        Returns:
            Narrative summary string.
        """
        prompt = self._prompts.render(
            "summary",
            artefacts=[r.model_dump(mode="json") for r in ranked_artefacts],
        )
        return self._call_llm(prompt)

    def _call_llm(self, prompt: str) -> str:
        """Send a prompt to the local LLaMA-3 API.

        Prefer ``OllamaClient`` when injected; otherwise use sync httpx.

        Args:
            prompt: Fully rendered prompt text.

        Returns:
            Model response text.

        Raises:
            LLMConnectionError: If the local API cannot be reached.
            LLMTimeoutError: If the request times out.
            LLMResponseError: If the response payload is malformed.
        """
        if self._ollama is not None:
            return self._call_via_ollama(prompt)

        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "system": self._config.system_prompt,
            "stream": False,
            "options": {
                "temperature": self._config.temperature,
                "num_predict": self._config.num_predict,
                "top_p": self._config.top_p,
                "repeat_penalty": self._config.repeat_penalty,
            },
        }
        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="LLM_REQUEST",
            evidence_id="n/a",
            details={
                "model": self._config.model,
                "prompt_chars": len(prompt),
                "api_host": urlparse(self._config.api_url).hostname,
            },
        )
        try:
            with httpx.Client(timeout=self._config.request_timeout_seconds) as client:
                response = client.post(self._config.generate_url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            raise LLMConnectionError(
                "Failed to connect to local LLM API",
                context={"api_url": self._config.api_url},
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                "Local LLM API request timed out",
                context={
                    "api_url": self._config.api_url,
                    "timeout_seconds": self._config.request_timeout_seconds,
                },
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMConnectionError(
                f"Local LLM API HTTP error: {exc}",
                context={"api_url": self._config.api_url},
            ) from exc
        except ValueError as exc:
            raise LLMResponseError(
                "Local LLM API returned non-JSON response",
                context={"api_url": self._config.api_url},
            ) from exc

        text = data.get("response")
        if not isinstance(text, str):
            raise LLMResponseError(
                "Local LLM API response missing 'response' string field",
                context={"keys": list(data.keys())},
            )
        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="LLM_RESPONSE",
            evidence_id="n/a",
            details={
                "model": self._config.model,
                "response_chars": len(text),
            },
        )
        return text

    def _call_via_ollama(self, prompt: str) -> str:
        """Bridge sync analyser calls onto async ``OllamaClient.generate``."""
        assert self._ollama is not None

        async def _run() -> str:
            result = await self._ollama.generate(prompt)
            return result.text

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_run())
        # Already in an event loop — run in a dedicated thread.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_run())).result()

    def _parse_classification_response(
        self,
        response: str,
        artefacts: list[Artefact],
    ) -> list[RankedArtefact]:
        """Parse classification JSON into ranked artefacts.

        Malformed output falls back to INFORMATIONAL with a warning.

        Args:
            response: Raw LLM response text.
            artefacts: Original artefacts to match.

        Returns:
            List of ``RankedArtefact`` instances.
        """
        by_id = {artefact.artefact_id: artefact for artefact in artefacts}
        parsed = self._extract_json_object(response)
        classifications = []
        if isinstance(parsed, dict):
            raw_list = parsed.get("classifications", [])
            if isinstance(raw_list, list):
                classifications = raw_list

        ranked: list[RankedArtefact] = []
        seen: set[str] = set()
        for item in classifications:
            if not isinstance(item, dict):
                continue
            artefact_id = str(item.get("artefact_id", ""))
            artefact = by_id.get(artefact_id)
            if artefact is None:
                continue
            seen.add(artefact_id)
            level = self._parse_suspicion(item.get("suspicion_level"))
            score = self._parse_score(item.get("relevance_score"))
            ranked.append(
                RankedArtefact(
                    **artefact.model_dump(),
                    suspicion_level=level,
                    relevance_score=score,
                    classification_reasoning=str(item.get("reasoning", "")) or None,
                )
            )

        for artefact in artefacts:
            if artefact.artefact_id in seen:
                continue
            logger.warning(
                "Missing LLM classification for artefact %s; defaulting to INFORMATIONAL",
                artefact.artefact_id,
            )
            ranked.append(
                RankedArtefact(
                    **artefact.model_dump(),
                    suspicion_level=SuspicionLevel.INFORMATIONAL,
                    relevance_score=0.0,
                    classification_reasoning="Defaulted due to missing/malformed LLM output",
                )
            )
        return ranked

    def _apply_ranking_response(
        self,
        response: str,
        classified: list[RankedArtefact],
    ) -> list[RankedArtefact]:
        """Apply ranking JSON scores onto classified artefacts.

        Args:
            response: Raw LLM ranking response.
            classified: Previously classified artefacts.

        Returns:
            Artefacts with updated relevance scores, sorted by score descending.
        """
        by_id = {item.artefact_id: item for item in classified}
        parsed = self._extract_json_object(response)
        rankings: list[Any] = []
        if isinstance(parsed, dict):
            raw = parsed.get("rankings", [])
            if isinstance(raw, list):
                rankings = raw

        for item in rankings:
            if not isinstance(item, dict):
                continue
            artefact_id = str(item.get("artefact_id", ""))
            current = by_id.get(artefact_id)
            if current is None:
                continue
            score = self._parse_score(item.get("relevance_score"), current.relevance_score)
            reasoning = item.get("reasoning")
            by_id[artefact_id] = current.model_copy(
                update={
                    "relevance_score": score,
                    "classification_reasoning": (
                        str(reasoning)
                        if reasoning
                        else current.classification_reasoning
                    ),
                }
            )

        ordered = list(by_id.values())
        ordered.sort(key=lambda item: item.relevance_score, reverse=True)
        return ordered

    def _health_url(self) -> str:
        """Derive a local health-check URL from the Ollama base URL."""
        return self._config.tags_url

    @staticmethod
    def _assert_local_endpoint(api_url: str) -> None:
        """Reject non-local LLM endpoints to preserve chain-of-custody."""
        host = urlparse(api_url).hostname or ""
        if host not in _LOCAL_HOSTS:
            raise LLMConnectionError(
                f"Non-local LLM endpoint forbidden for chain-of-custody: {api_url}",
                context={"api_url": api_url, "host": host},
            )

    @staticmethod
    def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
        """Extract the first JSON object from an LLM response."""
        try:
            loaded = json.loads(text)
            return loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                logger.warning("Malformed LLM JSON; no object found")
                return None
            try:
                loaded = json.loads(match.group(0))
                return loaded if isinstance(loaded, dict) else None
            except json.JSONDecodeError:
                logger.warning("Malformed LLM JSON; parse failed after extraction")
                return None

    @staticmethod
    def _parse_suspicion(value: Any) -> SuspicionLevel:
        """Parse a suspicion level with INFORMATIONAL fallback."""
        try:
            return SuspicionLevel(str(value).strip().lower())
        except Exception:  # noqa: BLE001
            logger.warning("Unknown suspicion level %r; defaulting to INFORMATIONAL", value)
            return SuspicionLevel.INFORMATIONAL

    @staticmethod
    def _parse_score(value: Any, default: float = 0.0) -> float:
        """Parse a relevance score clamped to [0.0, 1.0]."""
        try:
            score = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, score))
