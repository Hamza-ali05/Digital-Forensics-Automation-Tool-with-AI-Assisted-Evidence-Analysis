"""LLM-assisted relevance ranking merged with rule-based scores."""

from __future__ import annotations

import logging
import time
from typing import Optional

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.llm.client import OllamaClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.ranking.parser import RankingResponseParser
from dfat.ai_engine.ranking.prompts import RankingPromptBuilder
from dfat.core.enums import PipelineStage, SuspicionLevel
from dfat.core.models.artefact import Artefact, RankedArtefact
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)

_LLM_WEIGHT = 0.4
_RULE_WEIGHT = 0.6

_SUSPICION_ORDER: dict[SuspicionLevel, int] = {
    SuspicionLevel.CRITICAL: 0,
    SuspicionLevel.HIGH: 1,
    SuspicionLevel.MEDIUM: 2,
    SuspicionLevel.LOW: 3,
    SuspicionLevel.INFORMATIONAL: 4,
}


class LLMRelevanceRanker:
    """Rank artefacts using LLM scores merged with optional rule-based scores."""

    def __init__(
        self,
        ollama_client: OllamaClient,
        prompt_builder: RankingPromptBuilder,
        response_parser: RankingResponseParser,
        audit_logger: ForensicAuditLogger,
        config: LLMConfig,
    ) -> None:
        """Initialise the relevance ranker.

        Args:
            ollama_client: Low-level Ollama HTTP client.
            prompt_builder: Ranking prompt builder.
            response_parser: Ranking response parser.
            audit_logger: Forensic audit logger (metadata only).
            config: LLM configuration.
        """
        self._ollama = ollama_client
        self._prompt_builder = prompt_builder
        self._parser = response_parser
        self._audit_logger = audit_logger
        self._config = config

    async def rank(
        self,
        classified: list[ClassificationResult],
        artefacts: list[Artefact],
        rule_based_scores: Optional[dict[str, float]] = None,
    ) -> list[RankedArtefact]:
        """Produce sorted ``RankedArtefact`` list from classification + scores.

        Weighted merge (when rule scores are provided)::

            final_score = 0.4 * llm_score + 0.6 * rule_based_score

        Missing LLM scores fall back to rule-based only (or ``0.0``).

        Args:
            classified: Classification results.
            artefacts: Source artefacts.
            rule_based_scores: Optional Prompt 4 rule-engine scores by ID.

        Returns:
            Ranked artefacts sorted by suspicion (CRITICAL first) then score.
        """
        if not classified:
            return []

        started = time.perf_counter()
        rule_scores = rule_based_scores or {}
        artefact_by_id = {item.artefact_id: item for item in artefacts}
        classified_ids = [item.artefact_id for item in classified]

        prompt = self._prompt_builder.build_prompt(classified, artefacts)
        llm_scores: dict[str, tuple[float, str]] = {}
        try:
            response = await self._ollama.generate(prompt)
            llm_scores = self._parser.parse(response.text, classified_ids)
        except Exception as exc:  # noqa: BLE001 — fall back to rule scores
            logger.warning("LLM ranking failed; using rule-based scores only: %s", exc)

        ranked: list[RankedArtefact] = []
        for result in classified:
            artefact = artefact_by_id.get(result.artefact_id)
            if artefact is None:
                logger.warning(
                    "Skipping classification without matching artefact: %s",
                    result.artefact_id,
                )
                continue

            llm_entry = llm_scores.get(result.artefact_id)
            rule_score = rule_scores.get(result.artefact_id)
            final_score, ranking_reason = self._merge_scores(llm_entry, rule_score)

            reasoning_parts = [result.reasoning.strip()] if result.reasoning else []
            if ranking_reason:
                reasoning_parts.append(ranking_reason)
            classification_reasoning = " | ".join(reasoning_parts) or None

            ranked.append(
                RankedArtefact(
                    **artefact.model_dump(),
                    suspicion_level=result.suspicion_level,
                    relevance_score=final_score,
                    classification_reasoning=classification_reasoning,
                )
            )

        ranked.sort(
            key=lambda item: (
                _SUSPICION_ORDER.get(item.suspicion_level, 99),
                -item.relevance_score,
            )
        )

        duration_ms = (time.perf_counter() - started) * 1000.0
        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="LLM_RANKING",
            evidence_id="n/a",
            details={
                "artefact_count": len(ranked),
                "llm_score_count": len(llm_scores),
                "rule_score_count": len(rule_scores),
                "model": self._config.model,
                "llm_weight": _LLM_WEIGHT,
                "rule_weight": _RULE_WEIGHT,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return ranked

    @staticmethod
    def _merge_scores(
        llm_entry: Optional[tuple[float, str]],
        rule_score: Optional[float],
    ) -> tuple[float, str]:
        """Combine LLM and rule-based scores with rule weight preferred.

        Returns:
            ``(final_score, ranking_reasoning)``.
        """
        llm_score = llm_entry[0] if llm_entry is not None else None
        ranking_reason = llm_entry[1] if llm_entry is not None else ""

        if llm_score is not None and rule_score is not None:
            final = (_LLM_WEIGHT * llm_score) + (_RULE_WEIGHT * float(rule_score))
            return max(0.0, min(1.0, final)), ranking_reason
        if llm_score is not None:
            return llm_score, ranking_reason
        if rule_score is not None:
            return max(0.0, min(1.0, float(rule_score))), ranking_reason
        return 0.0, ranking_reason
