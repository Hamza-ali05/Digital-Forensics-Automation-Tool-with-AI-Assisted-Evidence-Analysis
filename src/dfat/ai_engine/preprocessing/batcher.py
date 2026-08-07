"""Batch large artefact lists to fit LLM context windows."""

from __future__ import annotations

from collections import defaultdict

from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact

_CATEGORY_ORDER: tuple[ArtefactCategory, ...] = (
    ArtefactCategory.INJECTED_CODE,
    ArtefactCategory.NETWORK_CONNECTION,
    ArtefactCategory.REGISTRY_KEY,
    ArtefactCategory.RUNNING_PROCESS,
    ArtefactCategory.EVENT_LOG,
    ArtefactCategory.BROWSER_HISTORY,
    ArtefactCategory.FILESYSTEM_METADATA,
)


class ArtefactBatcher:
    """Split artefacts into token-budgeted batches, preferring category cohesion."""

    def __init__(
        self,
        max_tokens_per_batch: int = 6000,
        serializer: ArtefactSerializer | None = None,
    ) -> None:
        """Initialise the batcher.

        Args:
            max_tokens_per_batch: Estimated token budget per batch.
            serializer: Serializer used for token estimation.
        """
        self._max_tokens = max(1, max_tokens_per_batch)
        self._serializer = serializer or ArtefactSerializer()

    def estimate_batch_tokens(self, artefacts: list[Artefact]) -> int:
        """Estimate tokens for a batch using compact classification serialisation.

        Args:
            artefacts: Artefacts in the candidate batch.

        Returns:
            Estimated token count (``chars / 4``).
        """
        if not artefacts:
            return 0
        text = self._serializer.serialize_for_classification(artefacts)
        return max(1, (len(text) + 3) // 4)

    def create_batches(self, artefacts: list[Artefact]) -> list[list[Artefact]]:
        """Split artefacts into batches within the token budget.

        Artefacts of the same category are kept together when possible by
        processing categories in priority order and packing greedily.

        Args:
            artefacts: Full artefact list.

        Returns:
            List of non-empty batches.
        """
        if not artefacts:
            return []

        by_category: dict[ArtefactCategory, list[Artefact]] = defaultdict(list)
        for artefact in artefacts:
            by_category[artefact.category].append(artefact)

        ordered: list[Artefact] = []
        for category in _CATEGORY_ORDER:
            ordered.extend(by_category.pop(category, []))
        for remaining in by_category.values():
            ordered.extend(remaining)

        batches: list[list[Artefact]] = []
        current: list[Artefact] = []

        for artefact in ordered:
            candidate = current + [artefact]
            if current and self.estimate_batch_tokens(candidate) > self._max_tokens:
                batches.append(current)
                current = [artefact]
                # Single oversized artefact still forms its own batch.
                if self.estimate_batch_tokens(current) > self._max_tokens:
                    batches.append(current)
                    current = []
            else:
                current = candidate

        if current:
            batches.append(current)
        return batches
