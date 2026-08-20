"""RAG-enhanced artefact analyser wrapping ``LocalLLMClient``.

Does not replace ``LocalLLMClient`` — both remain available via the DI
container. ``TriageStage`` receives this analyser when ``ai_engine.use_rag``
is enabled.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator, Optional

from dfat.ai_engine.analyzer import LocalLLMClient
from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.core.enums import PipelineStage
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.knowledge.rag.context_builder import RAGContextBuilder
from dfat.knowledge.rag.rag_prompts import RAGPromptTemplates

if TYPE_CHECKING:
    from dfat.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class _BoundRAGTemplates:
    """Adapt ``RAGPromptTemplates`` to the base ``templates.render(...)`` API."""

    def __init__(
        self,
        rag_prompts: RAGPromptTemplates,
        rag_context: str,
        source_attribution: list[str],
        base_templates: Any,
    ) -> None:
        self._rag_prompts = rag_prompts
        self._rag_context = rag_context
        self._source_attribution = source_attribution
        self._base = base_templates

    def render(self, template_name: str, **context: Any) -> str:
        """Render a RAG template, falling back to the original for ranking."""
        if template_name in {"classification", "summary", "qa", "explanation"}:
            return self._rag_prompts.render(
                template_name,
                rag_context=self._rag_context,
                source_attribution=self._source_attribution,
                **context,
            )
        return self._base.render(template_name, **context)

    def get_template_version(self) -> str:
        """Return the RAG prompt version."""
        return self._rag_prompts.get_template_version()


class RAGEnhancedAnalyzer(IArtefactAnalyzer):
    """Wraps ``LocalLLMClient`` with RAG context injection.

    Falls back to ``LocalLLMClient`` without RAG if the knowledge base is empty.
    Falls back to ``RuleBasedAnalyzer`` if the LLM is unavailable.

    Does not replace ``LocalLLMClient`` — both remain available via DI.
    Pipeline ``TriageStage`` selects which analyser to use based on configuration.
    """

    def __init__(
        self,
        llm_client: LocalLLMClient,
        context_builder: RAGContextBuilder,
        rag_prompts: RAGPromptTemplates,
        audit_service: AuditService,
    ) -> None:
        self.llm_client = llm_client
        self._context_builder = context_builder
        self._rag_prompts = rag_prompts
        self._audit = audit_service
        self._rule_fallback: Optional[RuleBasedAnalyzer] = None
        self._prompt_bind_lock = threading.Lock()

    @property
    def analyzer_name(self) -> str:
        """Return the stable analyser identifier."""
        return "RAGEnhancedLLaMA3"

    def is_available(self) -> bool:
        """Return True when the wrapped local LLM endpoint is reachable."""
        return self.llm_client.is_available()

    def analyze(self, artefact_set: ArtefactSet) -> list[RankedArtefact]:
        """Classify and rank artefacts (sync ``IArtefactAnalyzer`` entrypoint)."""
        return self._run_sync(self.analyze_async(artefact_set))

    def summarize(self, ranked_artefacts: list[RankedArtefact]) -> str:
        """Generate an investigative summary (sync ``IArtefactAnalyzer`` entrypoint)."""
        return self._run_sync(self.summarize_async(ranked_artefacts))

    async def analyze_async(self, artefact_set: ArtefactSet) -> list[RankedArtefact]:
        """Analyse artefacts, injecting RAG context when the knowledge base has hits."""
        if not self.llm_client.is_available():
            return await self._fallback_to_rules(
                artefact_set,
                reason="llm_unavailable",
            )

        context, sources = await self._safe_classification_context(artefact_set)
        if not context.strip():
            ranked = await self.llm_client.analyze_async(artefact_set)
            await self._audit.log_action(
                stage=PipelineStage.AI_TRIAGE,
                action="RAG_ANALYZER_FALLBACK",
                evidence_id=artefact_set.evidence_id,
                details={
                    "analyzer": self.analyzer_name,
                    "rag_used": False,
                    "reason": "empty_knowledge_base",
                    "fallback": self.llm_client.analyzer_name,
                    "artefact_count": len(ranked),
                    "contributing_datasets": [],
                },
            )
            return ranked

        with self._bind_rag_prompts(context, sources):
            ranked = await self.llm_client.analyze_async(artefact_set)

        annotated = self._annotate_rag_sources(ranked, sources)
        await self._audit.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="RAG_ANALYSIS_COMPLETED",
            evidence_id=artefact_set.evidence_id,
            details={
                "analyzer": self.analyzer_name,
                "rag_used": True,
                "contributing_datasets": sources,
                "artefact_count": len(annotated),
                "prompt_version": self._rag_prompts.get_template_version(),
            },
        )
        return annotated

    async def summarize_async(self, ranked_artefacts: list[RankedArtefact]) -> str:
        """Summarise ranked artefacts, injecting RAG context when available."""
        if not self.llm_client.is_available():
            fallback = self._rule_based_analyzer()
            await self._audit.log_action(
                stage=PipelineStage.AI_TRIAGE,
                action="RAG_SUMMARIZE_FALLBACK",
                evidence_id=self._evidence_id(ranked_artefacts),
                details={
                    "analyzer": self.analyzer_name,
                    "rag_used": False,
                    "reason": "llm_unavailable",
                    "fallback": fallback.analyzer_name,
                    "contributing_datasets": [],
                },
            )
            return fallback.summarize(ranked_artefacts)

        context, sources = await self._safe_summary_context(ranked_artefacts)
        if not context.strip():
            summary = await self.llm_client.summarize_async(ranked_artefacts)
            await self._audit.log_action(
                stage=PipelineStage.AI_TRIAGE,
                action="RAG_SUMMARIZE_FALLBACK",
                evidence_id=self._evidence_id(ranked_artefacts),
                details={
                    "analyzer": self.analyzer_name,
                    "rag_used": False,
                    "reason": "empty_knowledge_base",
                    "fallback": self.llm_client.analyzer_name,
                    "contributing_datasets": [],
                },
            )
            return summary

        with self._bind_rag_prompts(context, sources):
            summary = await self.llm_client.summarize_async(ranked_artefacts)

        await self._audit.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="RAG_SUMMARY_COMPLETED",
            evidence_id=self._evidence_id(ranked_artefacts),
            details={
                "analyzer": self.analyzer_name,
                "rag_used": True,
                "contributing_datasets": sources,
                "summary_chars": len(summary or ""),
                "prompt_version": self._rag_prompts.get_template_version(),
            },
        )
        return summary

    async def _safe_classification_context(
        self,
        artefact_set: ArtefactSet,
    ) -> tuple[str, list[str]]:
        try:
            return await self._context_builder.build_classification_context_with_sources(
                list(artefact_set.artefacts)
            )
        except Exception as exc:  # noqa: BLE001 — RAG must not degrade analysis
            logger.warning("RAG classification context failed; using standard prompts: %s", exc)
            return "", []

    async def _safe_summary_context(
        self,
        ranked: list[RankedArtefact],
    ) -> tuple[str, list[str]]:
        try:
            return await self._context_builder.build_summary_context_with_sources(ranked)
        except Exception as exc:  # noqa: BLE001 — RAG must not degrade analysis
            logger.warning("RAG summary context failed; using standard prompts: %s", exc)
            return "", []

    async def _fallback_to_rules(
        self,
        artefact_set: ArtefactSet,
        *,
        reason: str,
    ) -> list[RankedArtefact]:
        fallback = self._rule_based_analyzer()
        await self._audit.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="RAG_ANALYZER_FALLBACK",
            evidence_id=artefact_set.evidence_id,
            details={
                "analyzer": self.analyzer_name,
                "rag_used": False,
                "reason": reason,
                "fallback": fallback.analyzer_name,
                "contributing_datasets": [],
            },
        )
        return fallback.analyze(artefact_set)

    def _rule_based_analyzer(self) -> RuleBasedAnalyzer:
        if self._rule_fallback is None:
            self._rule_fallback = RuleBasedAnalyzer()
        return self._rule_fallback

    @contextmanager
    def _bind_rag_prompts(self, rag_context: str, sources: list[str]) -> Iterator[None]:
        """Temporarily swap LLM prompt templates for RAG-augmented versions.

        The actual generate/classify/rank/summarize calls stay on ``llm_client``
        internals; only the prompt text is swapped for the duration of the call.
        """
        classifier_builder = self.llm_client._classifier._prompt_builder
        summarizer_builder = self.llm_client._summarizer._prompt_builder
        original_cls = classifier_builder._templates
        original_sum = summarizer_builder._templates
        bound = _BoundRAGTemplates(
            self._rag_prompts,
            rag_context,
            sources,
            original_cls,
        )
        with self._prompt_bind_lock:
            classifier_builder._templates = bound
            summarizer_builder._templates = bound
            try:
                yield
            finally:
                classifier_builder._templates = original_cls
                summarizer_builder._templates = original_sum

    @staticmethod
    def _annotate_rag_sources(
        ranked: list[RankedArtefact],
        sources: list[str],
    ) -> list[RankedArtefact]:
        """Append contributing dataset names to ``classification_reasoning``."""
        source_text = ",".join(sources) if sources else "none"
        tag = f"[rag_sources: {source_text}]"
        annotated: list[RankedArtefact] = []
        for item in ranked:
            existing = (item.classification_reasoning or "").strip()
            if tag in existing:
                annotated.append(item)
                continue
            reasoning = f"{existing} {tag}".strip() if existing else tag
            item.classification_reasoning = reasoning
            annotated.append(item)
        return annotated

    @staticmethod
    def _evidence_id(ranked: list[RankedArtefact]) -> str:
        if not ranked:
            return "n/a"
        return ranked[0].source_evidence_id

    @staticmethod
    def _run_sync(coro):  # type: ignore[no-untyped-def]
        """Run an async coroutine from sync ``IArtefactAnalyzer`` methods."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
