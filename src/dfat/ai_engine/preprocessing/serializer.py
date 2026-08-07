"""Artefact-to-text serialization for local LLM prompts."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact

# IOC-relevant priority when truncating large artefact sets (highest first).
_CATEGORY_PRIORITY: tuple[ArtefactCategory, ...] = (
    ArtefactCategory.INJECTED_CODE,
    ArtefactCategory.NETWORK_CONNECTION,
    ArtefactCategory.REGISTRY_KEY,
    ArtefactCategory.RUNNING_PROCESS,
    ArtefactCategory.EVENT_LOG,
    ArtefactCategory.BROWSER_HISTORY,
    ArtefactCategory.FILESYSTEM_METADATA,
)

_HIGH_PLUS: frozenset[SuspicionLevel] = frozenset(
    {SuspicionLevel.CRITICAL, SuspicionLevel.HIGH}
)


class ArtefactSerializer:
    """Converts Artefact objects into text representations for LLM prompts."""

    def serialize_artefact(self, artefact: Artefact) -> str:
        """Format one artefact with ID, category, and ordered ``raw_data`` fields.

        Args:
            artefact: Artefact to serialise.

        Returns:
            Multi-line text block suitable for prompt embedding.
        """
        lines = [
            f"[{artefact.artefact_id}] Category: {artefact.category.value}",
        ]
        if artefact.source_path:
            lines.append(f"source_path: {artefact.source_path}")
        for key, value in self._ordered_raw_items(artefact.raw_data):
            lines.append(f"{key}: {self._format_value(value)}")
        return "\n".join(lines)

    def serialize_artefact_set(
        self,
        artefact_set: ArtefactSet,
        max_artefacts: int = 500,
    ) -> str:
        """Serialise an artefact set grouped by category with priority truncation.

        When ``len(artefacts) > max_artefacts``, artefacts from IOC-relevant
        categories are kept first (``INJECTED_CODE``, ``NETWORK_CONNECTION``, …).

        Args:
            artefact_set: Parsed artefact collection.
            max_artefacts: Maximum artefacts to include.

        Returns:
            Category-grouped text block.
        """
        selected = self._prioritise(list(artefact_set.artefacts), max_artefacts)
        by_category: dict[ArtefactCategory, list[Artefact]] = defaultdict(list)
        for artefact in selected:
            by_category[artefact.category].append(artefact)

        sections: list[str] = [
            f"Evidence: {artefact_set.evidence_id}",
            f"Artefacts included: {len(selected)} / {len(artefact_set.artefacts)}",
        ]
        for category in _CATEGORY_PRIORITY:
            items = by_category.get(category)
            if not items:
                continue
            sections.append(f"\n=== {category.value.upper()} ({len(items)}) ===")
            for artefact in items:
                sections.append(self.serialize_artefact(artefact))
                sections.append("")
        # Any unexpected categories (future-proof).
        for category, items in by_category.items():
            if category in _CATEGORY_PRIORITY:
                continue
            sections.append(f"\n=== {category.value.upper()} ({len(items)}) ===")
            for artefact in items:
                sections.append(self.serialize_artefact(artefact))
                sections.append("")
        return "\n".join(sections).rstrip() + "\n"

    def serialize_ranked_artefact(self, ranked: RankedArtefact) -> str:
        """Serialise a ranked artefact including suspicion and relevance.

        Args:
            ranked: Triaged artefact.

        Returns:
            Multi-line text including triage fields.
        """
        base = self.serialize_artefact(ranked)
        extra = [
            f"suspicion_level: {ranked.suspicion_level.value}",
            f"relevance_score: {ranked.relevance_score:.4f}",
        ]
        if ranked.classification_reasoning:
            extra.append(f"reasoning: {ranked.classification_reasoning}")
        return f"{base}\n" + "\n".join(extra)

    def serialize_for_classification(self, artefacts: list[Artefact]) -> str:
        """Compact one-line-per-artefact format for classification prompts.

        Args:
            artefacts: Artefacts to classify.

        Returns:
            Newline-separated compact records.
        """
        lines: list[str] = []
        for artefact in artefacts:
            raw = "; ".join(
                f"{key}={self._format_value(value)}"
                for key, value in self._ordered_raw_items(artefact.raw_data)
            )
            lines.append(
                f"[{artefact.artefact_id}] {artefact.category.value} | {raw}"
            )
        return "\n".join(lines)

    def serialize_for_summary(self, ranked: list[RankedArtefact]) -> str:
        """Summary format: detail for HIGH+ artefacts; stats for the rest.

        Args:
            ranked: Triaged artefacts.

        Returns:
            Summary-oriented prompt text.
        """
        high_plus = [item for item in ranked if item.suspicion_level in _HIGH_PLUS]
        others = [item for item in ranked if item.suspicion_level not in _HIGH_PLUS]

        counts: dict[str, int] = defaultdict(int)
        for item in ranked:
            counts[item.suspicion_level.value] += 1

        sections: list[str] = [
            f"Total artefacts: {len(ranked)}",
            "Suspicion distribution: "
            + ", ".join(f"{level}={counts[level]}" for level in sorted(counts)),
            f"High+ detailed: {len(high_plus)}; summarised others: {len(others)}",
        ]

        if high_plus:
            sections.append("\n=== HIGH / CRITICAL DETAIL ===")
            for item in sorted(
                high_plus,
                key=lambda a: a.relevance_score,
                reverse=True,
            ):
                sections.append(self.serialize_ranked_artefact(item))
                sections.append("")

        if others:
            sections.append("=== OTHER ARTEFACTS (STATISTICS) ===")
            by_cat: dict[str, int] = defaultdict(int)
            for item in others:
                by_cat[item.category.value] += 1
            for category, count in sorted(by_cat.items()):
                sections.append(f"- {category}: {count}")

        return "\n".join(sections).rstrip() + "\n"

    def _prioritise(
        self,
        artefacts: list[Artefact],
        max_artefacts: int,
    ) -> list[Artefact]:
        """Return up to ``max_artefacts`` ordered by IOC category priority."""
        if max_artefacts <= 0:
            return []
        if len(artefacts) <= max_artefacts:
            return list(artefacts)

        priority_index = {
            category: index for index, category in enumerate(_CATEGORY_PRIORITY)
        }

        def sort_key(artefact: Artefact) -> tuple[int, str]:
            return (
                priority_index.get(artefact.category, len(_CATEGORY_PRIORITY)),
                artefact.artefact_id,
            )

        ordered = sorted(artefacts, key=sort_key)
        return ordered[:max_artefacts]

    @staticmethod
    def _ordered_raw_items(raw_data: dict[str, Any]) -> list[tuple[str, Any]]:
        """Return ``raw_data`` items sorted by key for stable prompts."""
        return sorted(raw_data.items(), key=lambda item: item[0])

    @staticmethod
    def _format_value(value: Any) -> str:
        """Render a ``raw_data`` value as compact text."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (list, tuple)):
            return "[" + ", ".join(ArtefactSerializer._format_value(v) for v in value) + "]"
        if isinstance(value, dict):
            inner = ", ".join(
                f"{k}={ArtefactSerializer._format_value(v)}"
                for k, v in sorted(value.items(), key=lambda item: item[0])
            )
            return "{" + inner + "}"
        return str(value)
