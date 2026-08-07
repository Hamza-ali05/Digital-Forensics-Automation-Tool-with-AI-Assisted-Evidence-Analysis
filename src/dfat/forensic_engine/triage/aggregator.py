"""Triage result aggregation — summary statistics for reporting."""

from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import SuspicionLevel
from dfat.core.models.artefact import RankedArtefact
from dfat.forensic_engine.processing.ioc_detector import IOCMatch
from dfat.forensic_engine.processing.timeline import Timeline


class TriageSummary(BaseModel):
    """Aggregated triage output prepared for the reporting stage.

    Attributes:
        total_artefacts: Count of ranked artefacts.
        by_suspicion: Counts keyed by ``SuspicionLevel`` value.
        critical_artefacts: Up to 10 highest-priority CRITICAL (then HIGH) items.
        ioc_count: Number of IOC matches considered.
        timeline_range: Human-readable earliest→latest span, if available.
        key_findings: Top 5 most suspicious artefacts with reasoning.
        triage_duration_seconds: Wall-clock time spent aggregating.
    """

    model_config = ConfigDict(frozen=False)

    total_artefacts: int = 0
    by_suspicion: dict[str, int] = Field(default_factory=dict)
    critical_artefacts: list[dict[str, Any]] = Field(default_factory=list)
    ioc_count: int = 0
    timeline_range: Optional[str] = None
    key_findings: list[str] = Field(default_factory=list)
    triage_duration_seconds: float = 0.0


class TriageAggregator:
    """Aggregate ranked triage results into a reporting-ready summary."""

    def aggregate(
        self,
        ranked: list[RankedArtefact],
        timeline: Timeline,
        ioc_matches: list[IOCMatch],
    ) -> TriageSummary:
        """Compute summary statistics from triage outputs.

        Args:
            ranked: Ranked artefacts from the triage engine (preferably sorted).
            timeline: Chronological timeline of timestamped artefacts.
            ioc_matches: IOC detector matches for the same evidence set.

        Returns:
            ``TriageSummary`` with counts, top critical items, and key findings.
        """
        started = time.perf_counter()

        by_suspicion = self._count_by_suspicion(ranked)
        critical_artefacts = self._top_critical(ranked, limit=10)
        key_findings = self._key_findings(ranked, limit=5)
        timeline_range = self._timeline_range(timeline)

        duration = time.perf_counter() - started
        return TriageSummary(
            total_artefacts=len(ranked),
            by_suspicion=by_suspicion,
            critical_artefacts=critical_artefacts,
            ioc_count=len(ioc_matches),
            timeline_range=timeline_range,
            key_findings=key_findings,
            triage_duration_seconds=round(duration, 6),
        )

    @staticmethod
    def _count_by_suspicion(ranked: list[RankedArtefact]) -> dict[str, int]:
        """Return counts for every ``SuspicionLevel``, including zeros."""
        counts = {level.value: 0 for level in SuspicionLevel}
        for artefact in ranked:
            counts[artefact.suspicion_level.value] = (
                counts.get(artefact.suspicion_level.value, 0) + 1
            )
        return counts

    def _top_critical(
        self,
        ranked: list[RankedArtefact],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return serialisable summaries of the top critical artefacts.

        Prefers ``CRITICAL`` items; backfills with ``HIGH`` if fewer than
        ``limit`` critical findings exist.
        """
        ordered = sorted(
            ranked,
            key=lambda item: (
                0 if item.suspicion_level is SuspicionLevel.CRITICAL else
                1 if item.suspicion_level is SuspicionLevel.HIGH else
                2,
                -item.relevance_score,
            ),
        )
        selected = [
            item
            for item in ordered
            if item.suspicion_level
            in {SuspicionLevel.CRITICAL, SuspicionLevel.HIGH}
        ][:limit]

        return [self._artefact_summary(item) for item in selected]

    def _key_findings(
        self,
        ranked: list[RankedArtefact],
        limit: int = 5,
    ) -> list[str]:
        """Build top-N key finding strings with suspicion and reasoning."""
        ordered = sorted(ranked, key=lambda item: -item.relevance_score)
        findings: list[str] = []
        for item in ordered[:limit]:
            label = self._artefact_label(item)
            reasoning = (item.classification_reasoning or "").strip()
            if len(reasoning) > 240:
                reasoning = reasoning[:237] + "..."
            if reasoning:
                findings.append(
                    f"[{item.suspicion_level.value.upper()}] "
                    f"{label} (score={item.relevance_score:.2f}): {reasoning}"
                )
            else:
                findings.append(
                    f"[{item.suspicion_level.value.upper()}] "
                    f"{label} (score={item.relevance_score:.2f})"
                )
        return findings

    @staticmethod
    def _timeline_range(timeline: Timeline) -> Optional[str]:
        """Format the timeline earliest→latest range, if present."""
        if timeline.earliest is None or timeline.latest is None:
            if timeline.entry_count == 0:
                return None
            return None
        start = timeline.earliest.isoformat()
        end = timeline.latest.isoformat()
        duration = timeline.duration_seconds
        return (
            f"{start} -> {end} "
            f"({timeline.entry_count} events, {duration:.0f}s span)"
        )

    @staticmethod
    def _artefact_summary(artefact: RankedArtefact) -> dict[str, Any]:
        """Compact dict representation for critical artefact listings."""
        return {
            "artefact_id": artefact.artefact_id,
            "category": artefact.category.value,
            "suspicion_level": artefact.suspicion_level.value,
            "relevance_score": artefact.relevance_score,
            "source_path": artefact.source_path,
            "classification_reasoning": artefact.classification_reasoning,
            "raw_data": artefact.raw_data,
        }

    @staticmethod
    def _artefact_label(artefact: RankedArtefact) -> str:
        """Short identifying label for key findings."""
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        category = artefact.category.value
        for key in (
            "name",
            "process_name",
            "path",
            "filename",
            "url",
            "key_path",
            "remote_address",
            "event_id",
        ):
            value = raw.get(key)
            if value not in (None, ""):
                return f"{category}:{value}"
        return f"{category}:{artefact.artefact_id[:8]}"
