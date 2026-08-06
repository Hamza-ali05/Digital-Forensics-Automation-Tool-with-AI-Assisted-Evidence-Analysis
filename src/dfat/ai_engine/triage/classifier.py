"""Artefact classification via local LLM with INFORMATIONAL fallback."""

from __future__ import annotations

import logging
from typing import Any

from dfat.ai_engine.llm.client import LocalLLMClient
from dfat.core.enums import SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact

logger = logging.getLogger(__name__)


class ArtefactClassifier:
    """Classify artefacts using the local LLM client when available."""

    def __init__(self, llm_client: LocalLLMClient) -> None:
        """Initialise the classifier.

        Args:
            llm_client: Local LLaMA-3 client.
        """
        self._llm_client = llm_client

    def classify(self, artefacts: list[Artefact]) -> list[RankedArtefact]:
        """Classify artefacts by suspicion level.

        Args:
            artefacts: Artefacts to classify.

        Returns:
            Ranked artefacts. If the LLM is unavailable, all items are
            returned as INFORMATIONAL.
        """
        if not artefacts:
            return []
        if not self._llm_client.is_available():
            logger.warning("LLM unavailable; classifying all artefacts as INFORMATIONAL")
            return [
                RankedArtefact(
                    **artefact.model_dump(),
                    suspicion_level=SuspicionLevel.INFORMATIONAL,
                    relevance_score=0.0,
                    classification_reasoning="LLM unavailable; default INFORMATIONAL",
                )
                for artefact in artefacts
            ]

        artefact_set = ArtefactSet(
            evidence_id=artefacts[0].source_evidence_id,
            artefacts=artefacts,
            categories_present=sorted(
                {item.category for item in artefacts},
                key=lambda category: category.value,
            ),
        )
        # Use classification stage only: call analyze then preserve levels.
        return self._llm_client.analyze(artefact_set)

    def _parse_classification_response(
        self,
        response: str,
        artefacts: list[Artefact],
    ) -> list[RankedArtefact]:
        """Parse an LLM classification response.

        Args:
            response: Raw LLM response text.
            artefacts: Artefacts to match against.

        Returns:
            Parsed ranked artefacts with INFORMATIONAL defaults for gaps.
        """
        return self._llm_client._parse_classification_response(response, artefacts)
