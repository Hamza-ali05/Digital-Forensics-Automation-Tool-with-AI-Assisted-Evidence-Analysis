"""Assembled local LLaMA-3 analyser implementing ``IArtefactAnalyzer``.

Known limitation: Uses base LLaMA-3 rather than a domain-fine-tuned
variant (Sharma et al., 2025 ForensicLLM). Fine-tuning is documented
as a future improvement path. Structured JSON remains the authoritative
evidential record (Scanlon et al., 2023).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from typing import Optional

from dfat.ai_engine.assistance.investigator_qa import (
    InvestigatorQAAssistant,
    QAResponse,
)
from dfat.ai_engine.caching.response_cache import AIResponseCache
from dfat.ai_engine.classification.classifier import LLMArtefactClassifier
from dfat.ai_engine.explanation.explainer import (
    ArtefactExplanation,
    ArtefactExplainer,
    InMemoryResponseCache,
)
from dfat.ai_engine.llm.client import OllamaClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.monitoring.ai_monitor import AIMonitor
from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.ai_engine.ranking.ranker import LLMRelevanceRanker
from dfat.ai_engine.summarization.narrative import NarrativeFormatter
from dfat.ai_engine.summarization.summarizer import LLMInvestigativeSummarizer
from dfat.ai_engine.validation.response_validator import AIResponseValidator
from dfat.core.exceptions import LLMConnectionError
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)

_HEALTH_CACHE_SECONDS = 30.0


class LocalLLMClient(IArtefactAnalyzer):
    """Complete ``IArtefactAnalyzer`` implementation using local LLaMA-3.

    Coordinates preprocessing, classification, ranking, summarization,
    validation, caching, and monitoring.

    Known limitation: Uses base LLaMA-3 rather than a domain-fine-tuned
    variant (Sharma et al., 2025 ForensicLLM). Fine-tuning is documented
    as a future improvement path.
    """

    def __init__(
        self,
        config: LLMConfig,
        ollama_client: OllamaClient,
        connection_manager: LLMConnectionManager,
        classifier: LLMArtefactClassifier,
        ranker: LLMRelevanceRanker,
        summarizer: LLMInvestigativeSummarizer,
        validator: AIResponseValidator,
        cache: AIResponseCache,
        monitor: AIMonitor,
        audit_logger: ForensicAuditLogger,
        *,
        explainer: Optional[ArtefactExplainer] = None,
        qa_assistant: Optional[InvestigatorQAAssistant] = None,
        narrative_formatter: Optional[NarrativeFormatter] = None,
    ) -> None:
        """Initialise the assembled local LLM analyser."""
        self._config = config
        self._ollama = ollama_client
        self._connection = connection_manager
        self._classifier = classifier
        self._ranker = ranker
        self._summarizer = summarizer
        self._validator = validator
        self._cache = cache
        self._monitor = monitor
        self._audit_logger = audit_logger
        self._explainer = explainer
        self._qa = qa_assistant
        self._narrative = narrative_formatter or NarrativeFormatter()
        self._health_cached: Optional[bool] = None
        self._health_cached_at: float = 0.0

    @property
    def analyzer_name(self) -> str:
        """Return the stable analyser identifier."""
        return "LocalLLaMA3Client"

    def is_available(self) -> bool:
        """Return True when the local Ollama endpoint is healthy.

        Caches the result for 30 seconds to avoid repeated health checks.
        """
        now = time.monotonic()
        if (
            self._health_cached is not None
            and (now - self._health_cached_at) < _HEALTH_CACHE_SECONDS
        ):
            return self._health_cached
        try:
            status = self._run_sync(self._connection.check_health())
            self._health_cached = bool(status.is_healthy)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LLM health check failed: %s", exc)
            self._health_cached = False
        self._health_cached_at = now
        return bool(self._health_cached)

    def analyze(self, artefact_set: ArtefactSet) -> list[RankedArtefact]:
        """Classify and rank artefacts (sync ``IArtefactAnalyzer`` entrypoint)."""
        return self._run_sync(self.analyze_async(artefact_set))

    def summarize(self, ranked_artefacts: list[RankedArtefact]) -> str:
        """Generate an investigative summary (sync ``IArtefactAnalyzer`` entrypoint)."""
        return self._run_sync(self.summarize_async(ranked_artefacts))

    async def analyze_async(self, artefact_set: ArtefactSet) -> list[RankedArtefact]:
        """Async analyse pipeline: classify → validate → rank → monitor."""
        if not self.is_available():
            raise LLMConnectionError(
                "Local LLM is unavailable for analyse()",
                context={"api_url": self._config.base_url},
            )

        started = time.perf_counter()
        artefacts = list(artefact_set.artefacts)
        request_id = await self._monitor.log_llm_request(
            request_type="analyze",
            model=self._config.model,
            prompt_tokens=max(1, len(artefacts) * 32),
            job_id=artefact_set.evidence_id,
        )

        classifications = await self._classifier.classify(artefacts)
        validation = self._validator.validate_classification(classifications, artefacts)
        if validation.hallucination_report and validation.hallucination_report.risk_level != "low":
            await self._monitor.log_hallucination_detected(
                request_id,
                validation.hallucination_report,
            )

        rule_scores: dict[str, float] = {}
        for artefact in artefacts:
            raw_score = artefact.metadata.get("rule_score")
            if raw_score is None:
                raw_score = artefact.metadata.get("rule_based_score")
            if raw_score is not None:
                try:
                    rule_scores[artefact.artefact_id] = float(raw_score)
                except (TypeError, ValueError):
                    continue

        ranked = await self._ranker.rank(
            classifications,
            artefacts,
            rule_based_scores=rule_scores or None,
        )

        duration_ms = (time.perf_counter() - started) * 1000.0
        avg_conf = (
            sum(item.confidence for item in classifications) / len(classifications)
            if classifications
            else 0.0
        )
        await self._monitor.log_classification(
            job_id=artefact_set.evidence_id,
            artefact_count=len(artefacts),
            results_count=len(ranked),
            avg_confidence=avg_conf,
            duration_ms=duration_ms,
        )
        await self._monitor.log_llm_response(
            request_id=request_id,
            completion_tokens=len(ranked) * 16,
            duration_ms=duration_ms,
            success=True,
            cache_hit=False,
        )
        return ranked

    async def summarize_async(self, ranked_artefacts: list[RankedArtefact]) -> str:
        """Async summarisation pipeline: summarize → validate → format → monitor."""
        if not self.is_available():
            raise LLMConnectionError(
                "Local LLM is unavailable for summarize()",
                context={"api_url": self._config.base_url},
            )

        started = time.perf_counter()
        request_id = await self._monitor.log_llm_request(
            request_type="summarize",
            model=self._config.model,
            prompt_tokens=max(1, len(ranked_artefacts) * 48),
            job_id="n/a",
        )

        summary = await self._summarizer.generate_summary(ranked_artefacts)
        validation = self._validator.validate_summary(summary, ranked_artefacts)
        if validation.hallucination_report and validation.hallucination_report.risk_level != "low":
            await self._monitor.log_hallucination_detected(
                request_id,
                validation.hallucination_report,
            )
            if validation.hallucination_report.clean_response:
                summary.full_text = validation.hallucination_report.clean_response

        evidence_id = (
            ranked_artefacts[0].source_evidence_id if ranked_artefacts else "n/a"
        )
        formatted = self._narrative.format_narrative(
            summary,
            ranked_artefacts,
            case_name="DFAT Investigation",
            evidence_id=evidence_id,
        )

        duration_ms = (time.perf_counter() - started) * 1000.0
        await self._monitor.log_summarization(
            job_id=evidence_id,
            summary_length=len(formatted.full_text),
            confidence=formatted.confidence_score,
            duration_ms=duration_ms,
        )
        await self._monitor.log_llm_response(
            request_id=request_id,
            completion_tokens=max(1, len(formatted.full_text) // 4),
            duration_ms=duration_ms,
            success=True,
            cache_hit=False,
        )
        return formatted.full_text

    async def warm_response_cache(self) -> int:
        """Prime the response cache with common forensic prompt patterns."""
        return await self._cache.warm_common_patterns(
            model=self._config.model,
            temperature=self._config.temperature,
            generate=self._ollama.generate,
        )

    async def explain(self, artefact: RankedArtefact) -> ArtefactExplanation:
        """Delegate per-artefact explanation to ``ArtefactExplainer``."""
        explainer = self._ensure_explainer()
        return await explainer.explain_artefact(artefact)

    async def ask_question(
        self,
        question: str,
        artefact_set: ArtefactSet,
        ranked: list[RankedArtefact],
        conversation_history: Optional[list[dict[str, str]]] = None,
    ) -> QAResponse:
        """Delegate investigator Q&A to ``InvestigatorQAAssistant``."""
        assistant = self.get_qa_assistant()
        return await assistant.ask(
            question,
            artefact_set,
            ranked=ranked,
            conversation_history=conversation_history,
        )

    def get_qa_assistant(self) -> InvestigatorQAAssistant:
        """Return (lazily constructing) the investigator Q&A assistant."""
        return self._ensure_qa()

    def get_explainer(self) -> ArtefactExplainer:
        """Return (lazily constructing) the artefact explainer."""
        return self._ensure_explainer()

    def _ensure_explainer(self) -> ArtefactExplainer:
        if self._explainer is None:
            self._explainer = ArtefactExplainer(
                ollama_client=self._ollama,
                templates=ForensicPromptTemplates(),
                serializer=ArtefactSerializer(),
                response_cache=InMemoryResponseCache(),
                audit_logger=self._audit_logger,
            )
        return self._explainer

    def _ensure_qa(self) -> InvestigatorQAAssistant:
        if self._qa is None:
            from dfat.ai_engine.validation.response_validator import AIResponseValidator

            guard = AIResponseValidator.default_guard()
            self._qa = InvestigatorQAAssistant(
                ollama_client=self._ollama,
                templates=ForensicPromptTemplates(),
                serializer=ArtefactSerializer(),
                hallucination_guard=guard,
                response_cache=InMemoryResponseCache(),
                audit_logger=self._audit_logger,
            )
        return self._qa

    @staticmethod
    def _run_sync(coro):  # type: ignore[no-untyped-def]
        """Run an async coroutine from sync ``IArtefactAnalyzer`` methods."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
