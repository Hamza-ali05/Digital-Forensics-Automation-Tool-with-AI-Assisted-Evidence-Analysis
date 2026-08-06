"""Local LLaMA-3 HTTP client implementing ``IArtefactAnalyzer``.

Known limitation: base LLaMA-3 may produce less accurate forensic summaries
than a fine-tuned variant (Sharma et al., 2025). Structured JSON reporting
(Stage 4) remains the auditable record independent of LLM narrative
(Scanlon et al., 2023).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.core.enums import PipelineStage, SuspicionLevel
from dfat.core.exceptions import LLMConnectionError, LLMResponseError, LLMTimeoutError
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class LocalLLMClient(IArtefactAnalyzer):
    """Local-only LLaMA-3 client for artefact triage and summarisation."""

    def __init__(
        self,
        config: LLMConfig,
        audit_logger: ForensicAuditLogger,
        prompts: Optional[ForensicPromptTemplates] = None,
    ) -> None:
        """Initialise the local LLM client.

        Args:
            config: Local API configuration.
            audit_logger: Forensic audit logger (metadata only; no evidence body).
            prompts: Optional prompt template manager.
        """
        self._assert_local_endpoint(config.api_url)
        self._config = config
        self._audit_logger = audit_logger
        self._prompts = prompts or ForensicPromptTemplates()

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

        Args:
            prompt: Fully rendered prompt text.

        Returns:
            Model response text.

        Raises:
            LLMConnectionError: If the local API cannot be reached.
            LLMTimeoutError: If the request times out.
            LLMResponseError: If the response payload is malformed.
        """
        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "system": self._config.system_prompt,
            "stream": False,
            "options": {
                "temperature": self._config.temperature,
                "num_predict": self._config.max_tokens,
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
                response = client.post(self._config.api_url, json=payload)
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
        """Derive a local health-check URL from the generate endpoint."""
        parsed = urlparse(self._config.api_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        return f"{base}/api/tags"

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
