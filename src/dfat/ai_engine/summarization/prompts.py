"""Summarization prompt construction for investigative narratives."""

from __future__ import annotations

from typing import Optional

from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.optimization import PromptOptimizer
from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.ai_engine.preprocessing.truncator import TokenTruncator
from dfat.core.enums import SuspicionLevel
from dfat.core.models.artefact import RankedArtefact
from dfat.forensic_engine.processing.timeline import Timeline
from dfat.forensic_engine.triage.aggregator import TriageSummary

_HIGH_PLUS = frozenset({SuspicionLevel.CRITICAL, SuspicionLevel.HIGH})


class SummarizationPromptBuilder:
    """Build summarization prompts from ranked artefacts and triage context."""

    def __init__(
        self,
        templates: ForensicPromptTemplates | None = None,
        serializer: ArtefactSerializer | None = None,
        truncator: TokenTruncator | None = None,
        optimizer: PromptOptimizer | None = None,
        max_tokens: int = 6000,
    ) -> None:
        """Initialise the summarization prompt builder.

        Args:
            templates: Versioned forensic prompt templates.
            serializer: Artefact serializer for HIGH+ detail blocks.
            truncator: Token-aware truncator for prompt budgets.
            optimizer: Context-window optimizer that prefers HIGH/CRITICAL.
            max_tokens: Truncator max token window.
        """
        self._templates = templates or ForensicPromptTemplates()
        self._serializer = serializer or ArtefactSerializer()
        self._truncator = truncator or TokenTruncator(max_tokens=max_tokens)
        self._optimizer = optimizer or PromptOptimizer(truncator=self._truncator)
        self._max_tokens = max(1, max_tokens)

    def build_summary_prompt(
        self,
        ranked: list[RankedArtefact],
        timeline: Optional[Timeline] = None,
        triage_summary: Optional[TriageSummary] = None,
    ) -> str:
        """Render ``SUMMARY_TEMPLATE`` with stats, timeline, and HIGH+ detail.

        Args:
            ranked: Ranked artefacts from triage.
            timeline: Optional chronological timeline.
            triage_summary: Optional Prompt 4 triage aggregation.

        Returns:
            Rendered (and truncated if needed) summary prompt.
        """
        critical_count = sum(
            1 for item in ranked if item.suspicion_level is SuspicionLevel.CRITICAL
        )
        high_count = sum(
            1 for item in ranked if item.suspicion_level is SuspicionLevel.HIGH
        )
        categories = sorted({item.category.value for item in ranked})

        if triage_summary is not None:
            total_count = triage_summary.total_artefacts or len(ranked)
            critical_count = triage_summary.by_suspicion.get(
                SuspicionLevel.CRITICAL.value,
                critical_count,
            )
            high_count = triage_summary.by_suspicion.get(
                SuspicionLevel.HIGH.value,
                high_count,
            )
        else:
            total_count = len(ranked)

        detail_block = self._serializer.serialize_for_summary(ranked)
        high_plus = [item for item in ranked if item.suspicion_level in _HIGH_PLUS]
        # Prefer detailed HIGH+ blocks when present
        if high_plus:
            detail_parts = [
                self._serializer.serialize_ranked_artefact(item) for item in high_plus[:25]
            ]
            detail_block = "\n\n".join(detail_parts)

        extras: list[str] = []
        timeline_range = self._timeline_range(timeline, triage_summary)
        if timeline_range:
            extras.append(f"Timeline range: {timeline_range}")
        ioc_summary = self._ioc_summary(ranked, triage_summary)
        if ioc_summary:
            extras.append(f"IOC summary: {ioc_summary}")

        artefact_text = detail_block
        if extras:
            artefact_text = detail_block + "\n\n" + "\n".join(extras)

        prompt = self._templates.render(
            "summary",
            artefact_text=artefact_text,
            total_count=total_count,
            critical_count=critical_count,
            high_count=high_count,
            categories=", ".join(categories) if categories else "none",
        )
        return self._optimizer.optimize_for_context_window(prompt, self._max_tokens)

    @staticmethod
    def _timeline_range(
        timeline: Optional[Timeline],
        triage_summary: Optional[TriageSummary],
    ) -> str:
        """Build a human-readable timeline span string."""
        if triage_summary and triage_summary.timeline_range:
            return triage_summary.timeline_range
        if timeline is None or timeline.earliest is None or timeline.latest is None:
            return ""
        return f"{timeline.earliest.isoformat()} → {timeline.latest.isoformat()}"

    @staticmethod
    def _ioc_summary(
        ranked: list[RankedArtefact],
        triage_summary: Optional[TriageSummary],
    ) -> str:
        """Summarise IOC-related context for the prompt."""
        if triage_summary is not None and triage_summary.ioc_count:
            return f"{triage_summary.ioc_count} IOC match(es) from triage aggregation"
        indicators: list[str] = []
        for item in ranked:
            if item.suspicion_level not in _HIGH_PLUS:
                continue
            raw = item.raw_data or {}
            for key in ("suspicious_indicators", "ioc_indicators"):
                value = raw.get(key)
                if isinstance(value, list):
                    indicators.extend(str(v) for v in value)
        if not indicators:
            return ""
        unique = sorted(set(indicators))
        preview = ", ".join(unique[:10])
        return f"{len(unique)} indicator(s): {preview}"
