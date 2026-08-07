"""LLM-based artefact classification pipeline."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.classification.parser import ClassificationResponseParser
from dfat.ai_engine.classification.prompts import ClassificationPromptBuilder
from dfat.ai_engine.llm.client import OllamaClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.core.enums import PipelineStage, SuspicionLevel
from dfat.core.models.artefact import Artefact
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)

_FALLBACK_REASONING = "Classification failed — insufficient AI confidence."
_MISSING_REASONING = "Not classified by AI"


class ConfidenceScorer(Protocol):
    """Protocol for assigning confidence scores to classification results."""

    def score(self, result: ClassificationResult) -> float:
        """Return a confidence value in ``[0.0, 1.0]``."""


class DefaultConfidenceScorer:
    """Heuristic confidence until the dedicated explanation scorer lands."""

    def score(self, result: ClassificationResult) -> float:
        """Score based on reasoning quality and uncertainty markers."""
        reasoning = (result.reasoning or "").strip()
        if not reasoning or reasoning in {_FALLBACK_REASONING, _MISSING_REASONING}:
            return 0.1
        if "[UNCERTAIN]" in reasoning.upper() or "uncertain" in reasoning.lower():
            return 0.4
        if result.suspicion_level is SuspicionLevel.INFORMATIONAL and not result.ioc_indicators:
            return 0.5
        base = 0.7
        if result.ioc_indicators:
            base += 0.1
        if len(reasoning) >= 40:
            base += 0.1
        return min(1.0, base)


class LLMArtefactClassifier:
    """Classify artefacts via batched Ollama prompts and response parsing."""

    def __init__(
        self,
        ollama_client: OllamaClient,
        prompt_builder: ClassificationPromptBuilder,
        response_parser: ClassificationResponseParser,
        confidence_scorer: ConfidenceScorer,
        audit_logger: ForensicAuditLogger,
        config: LLMConfig,
    ) -> None:
        """Initialise the classifier.

        Args:
            ollama_client: Low-level Ollama HTTP client.
            prompt_builder: Classification prompt builder.
            response_parser: LLM response parser.
            confidence_scorer: Confidence assignment helper.
            audit_logger: Forensic audit logger (metadata only).
            config: LLM configuration.
        """
        self._ollama = ollama_client
        self._prompt_builder = prompt_builder
        self._parser = response_parser
        self._confidence = confidence_scorer
        self._audit_logger = audit_logger
        self._config = config

    async def classify(self, artefacts: list[Artefact]) -> list[ClassificationResult]:
        """Classify artefacts, batching when needed.

        Steps:
            1. Build prompt(s) via ``prompt_builder``.
            2. For each batch: call ``ollama_client.generate()``.
            3. Parse LLM responses into ``ClassificationResult`` objects.
            4. On parse failure per artefact: INFORMATIONAL defaults from parser.
            5. Log classification audit metadata (never evidence bodies).
            6. Return results aligned to input artefact order.

        Args:
            artefacts: Artefacts to classify.

        Returns:
            One ``ClassificationResult`` per input artefact.
        """
        if not artefacts:
            return []

        started = time.perf_counter()
        collected: dict[str, ClassificationResult] = {}

        batch_pairs = self._prompt_builder.iter_batches(artefacts)
        if not batch_pairs:
            batch_pairs = [(artefacts, self._prompt_builder.build_prompt(artefacts))]

        for batch, prompt in batch_pairs:
            batch_ids = [item.artefact_id for item in batch]
            try:
                response = await self._ollama.generate(prompt)
                raw_text = response.text
            except Exception as exc:  # noqa: BLE001 — per-batch soft failure
                logger.warning("Classification batch failed: %s", exc)
                raw_text = ""

            parsed_items = self._parser.parse(raw_text, batch_ids)
            for result in parsed_items:
                result.confidence = self._confidence.score(result)
                collected[result.artefact_id] = result

        results = [
            collected[artefact.artefact_id]
            for artefact in artefacts
            if artefact.artefact_id in collected
        ]

        duration_ms = (time.perf_counter() - started) * 1000.0
        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="LLM_CLASSIFICATION",
            evidence_id="n/a",
            details={
                "artefact_count": len(artefacts),
                "batch_count": len(batch_pairs),
                "model": self._config.model,
                "duration_ms": round(duration_ms, 2),
                "informational_fallbacks": sum(
                    1
                    for item in results
                    if item.reasoning in {_FALLBACK_REASONING, _MISSING_REASONING}
                ),
            },
        )
        return results
