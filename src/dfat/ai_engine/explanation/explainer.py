"""Per-artefact forensic explanation generation via local LLM.

Known limitation: base LLaMA-3 explanations are advisory and should be verified
against structured artefact ``raw_data`` (Scanlon et al., 2023; Sharma et al., 2025).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.llm.client import OllamaClient
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.core.enums import PipelineStage, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)

_HIGH_PLUS = frozenset({SuspicionLevel.CRITICAL, SuspicionLevel.HIGH})


class ArtefactExplanation(BaseModel):
    """Human-readable explanation of a single ranked artefact."""

    model_config = ConfigDict(frozen=False)

    artefact_id: str
    explanation_text: str
    forensic_significance: str = ""
    suggested_actions: list[str] = Field(default_factory=list)
    related_artefact_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    model_used: str = ""


class ResponseCache(Protocol):
    """Minimal cache protocol for explanation responses."""

    def get(self, key: str) -> Optional[Any]:
        """Return a cached value or ``None``."""

    def set(self, key: str, value: Any) -> None:
        """Store a value under ``key``."""


class InMemoryResponseCache:
    """Simple in-memory cache used until the dedicated caching module lands."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def __len__(self) -> int:
        return len(self._store)

    def __bool__(self) -> bool:
        """Caches are always truthy so ``cache or default`` keeps an empty cache."""
        return True


class ArtefactExplainer:
    """Generate and cache per-artefact forensic explanations."""

    def __init__(
        self,
        ollama_client: OllamaClient,
        templates: ForensicPromptTemplates,
        serializer: ArtefactSerializer,
        response_cache: ResponseCache,
        audit_logger: ForensicAuditLogger,
    ) -> None:
        """Initialise the explainer.

        Args:
            ollama_client: Low-level Ollama HTTP client.
            templates: Forensic prompt templates (includes EXPLANATION).
            serializer: Artefact text serializer.
            response_cache: Cache for explanation results.
            audit_logger: Forensic audit logger (metadata only).
        """
        self._ollama = ollama_client
        self._templates = templates
        self._serializer = serializer
        self._cache = response_cache
        self._audit_logger = audit_logger

    async def explain_artefact(self, artefact: RankedArtefact) -> ArtefactExplanation:
        """Explain a single artefact, using the cache when available.

        Args:
            artefact: Ranked artefact to explain.

        Returns:
            ``ArtefactExplanation`` (cached or freshly generated).
        """
        cache_key = self._cache_key(artefact)
        cached = self._cache.get(cache_key)
        if isinstance(cached, ArtefactExplanation):
            return cached
        if isinstance(cached, dict):
            explanation = ArtefactExplanation.model_validate(cached)
            return explanation

        started = time.perf_counter()
        prompt = self._templates.render(
            "explanation",
            artefact_text=self._serializer.serialize_ranked_artefact(artefact),
            suspicion_level=artefact.suspicion_level.value.upper(),
        )

        model_used = "unknown"
        raw_text = ""
        try:
            response = await self._ollama.generate(prompt)
            raw_text = response.text
            model_used = response.model or model_used
        except Exception as exc:  # noqa: BLE001 — soft failure
            logger.warning(
                "Explanation failed for %s: %s",
                artefact.artefact_id,
                exc,
            )
            raw_text = (
                f"[UNCERTAIN] Unable to generate LLM explanation for "
                f"{artefact.artefact_id}. Verify against structured JSON data. "
                f"Classification: {artefact.suspicion_level.value}."
            )

        explanation = self._parse_explanation(artefact, raw_text, model_used)
        self._cache.set(cache_key, explanation)

        duration_ms = (time.perf_counter() - started) * 1000.0
        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="LLM_EXPLANATION",
            evidence_id=artefact.source_evidence_id,
            details={
                "artefact_id": artefact.artefact_id,
                "suspicion_level": artefact.suspicion_level.value,
                "model": explanation.model_used,
                "confidence": explanation.confidence,
                "cached": False,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return explanation

    async def explain_batch(
        self,
        artefacts: list[RankedArtefact],
        max_concurrent: int = 5,
        *,
        high_plus_only: bool = True,
    ) -> list[ArtefactExplanation]:
        """Explain multiple artefacts with bounded concurrency.

        By default only CRITICAL and HIGH artefacts are explained to conserve
        LLM time.

        Args:
            artefacts: Ranked artefacts.
            max_concurrent: Maximum concurrent LLM explanation calls.
            high_plus_only: When True, skip MEDIUM/LOW/INFORMATIONAL.

        Returns:
            Explanations in the same order as the filtered input set.
        """
        targets = [
            item
            for item in artefacts
            if (not high_plus_only) or item.suspicion_level in _HIGH_PLUS
        ]
        if not targets:
            return []

        limit = max(1, max_concurrent)
        semaphore = asyncio.Semaphore(limit)
        active = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def _run(item: RankedArtefact) -> ArtefactExplanation:
            nonlocal active, max_seen
            async with semaphore:
                async with lock:
                    active += 1
                    max_seen = max(max_seen, active)
                try:
                    return await self.explain_artefact(item)
                finally:
                    async with lock:
                        active -= 1

        results = await asyncio.gather(*(_run(item) for item in targets))
        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="LLM_EXPLANATION_BATCH",
            evidence_id="n/a",
            details={
                "input_count": len(artefacts),
                "explained_count": len(targets),
                "max_concurrent": limit,
                "max_in_flight_observed": max_seen,
                "high_plus_only": high_plus_only,
            },
        )
        # Expose observed concurrency for tests via attribute
        self._last_max_in_flight = max_seen
        return list(results)

    def _cache_key(self, artefact: RankedArtefact) -> str:
        """Build a stable cache key from artefact identity and triage fields."""
        payload = (
            f"{artefact.artefact_id}|{artefact.suspicion_level.value}|"
            f"{artefact.relevance_score:.4f}|{artefact.classification_reasoning or ''}"
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"explain:{artefact.artefact_id}:{digest}"

    def _parse_explanation(
        self,
        artefact: RankedArtefact,
        text: str,
        model_used: str,
    ) -> ArtefactExplanation:
        """Parse LLM explanation text into structured fields."""
        cleaned = (text or "").strip()
        significance = self._section_after(
            cleaned,
            (
                r"1[.)]?\s*What this artefact represents",
                r"forensic significance",
                r"represents",
            ),
        ) or cleaned[:300]
        actions = self._extract_actions(cleaned)
        related = self._extract_related_ids(cleaned, artefact.artefact_id)
        confidence = 0.4 if "[UNCERTAIN]" in cleaned.upper() else 0.75
        if not cleaned:
            confidence = 0.1

        return ArtefactExplanation(
            artefact_id=artefact.artefact_id,
            explanation_text=cleaned,
            forensic_significance=significance.strip(),
            suggested_actions=actions,
            related_artefact_ids=related,
            confidence=confidence,
            model_used=model_used,
        )

    @staticmethod
    def _section_after(text: str, patterns: tuple[str, ...]) -> str:
        for pattern in patterns:
            match = re.search(
                pattern + r"\s*:?\s*(.*?)(?=\n\s*\d+[.)]|\Z)",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _extract_actions(text: str) -> list[str]:
        match = re.search(
            r"(?:3[.)]?\s*)?What investigative action[^\n]*\n?(.*?)(?=\n\s*(?:4[.)]|\Z))",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        block = match.group(1).strip() if match else ""
        if not block:
            return []
        actions: list[str] = []
        for line in block.splitlines():
            stripped = re.sub(r"^[-*•]\s+", "", line.strip())
            if stripped:
                actions.append(stripped)
        return actions[:5]

    @staticmethod
    def _extract_related_ids(text: str, self_id: str) -> list[str]:
        ids = re.findall(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            text,
            flags=re.IGNORECASE,
        )
        # Also catch simple art-* style IDs used in tests
        ids.extend(re.findall(r"\b(?:art|artefact)[-_][\w-]+\b", text, flags=re.IGNORECASE))
        unique: list[str] = []
        for item in ids:
            if item == self_id:
                continue
            if item not in unique:
                unique.append(item)
        return unique[:10]
