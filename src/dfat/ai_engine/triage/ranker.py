"""Deterministic relevance ranking for triaged artefacts."""

from __future__ import annotations

from dfat.core.enums import SuspicionLevel
from dfat.core.models.artefact import RankedArtefact

_SUSPICION_ORDER: dict[SuspicionLevel, int] = {
    SuspicionLevel.CRITICAL: 0,
    SuspicionLevel.HIGH: 1,
    SuspicionLevel.MEDIUM: 2,
    SuspicionLevel.LOW: 3,
    SuspicionLevel.INFORMATIONAL: 4,
}


class RelevanceRanker:
    """Sort ranked artefacts by suspicion level then relevance score."""

    def rank(self, classified: list[RankedArtefact]) -> list[RankedArtefact]:
        """Sort artefacts CRITICAL → HIGH → MEDIUM → LOW → INFORMATIONAL.

        Within the same suspicion level, sorts by ``relevance_score`` descending.
        Ordinal ranks are recorded in ``metadata['ordinal_rank']``.

        Args:
            classified: Classified artefacts to order.

        Returns:
            Newly ordered list of ranked artefacts.
        """
        ordered = sorted(
            classified,
            key=lambda item: (
                _SUSPICION_ORDER.get(item.suspicion_level, 99),
                -item.relevance_score,
            ),
        )
        result: list[RankedArtefact] = []
        for index, artefact in enumerate(ordered, start=1):
            metadata = dict(artefact.metadata)
            metadata["ordinal_rank"] = index
            result.append(artefact.model_copy(update={"metadata": metadata}))
        return result
