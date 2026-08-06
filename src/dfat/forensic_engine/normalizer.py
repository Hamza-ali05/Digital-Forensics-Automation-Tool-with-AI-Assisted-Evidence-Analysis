"""Artefact normalisation — merge parser outputs into one ArtefactSet."""

from __future__ import annotations

import logging

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet

logger = logging.getLogger(__name__)


class ArtefactNormalizer:
    """Merge and deduplicate artefact sets from multiple parsers."""

    def normalize(
        self,
        parser_results: list[ArtefactSet],
        evidence_id: str,
    ) -> ArtefactSet:
        """Merge parser outputs into a unified artefact set.

        Args:
            parser_results: Artefact sets produced by individual parsers.
            evidence_id: Source evidence identifier for the merged set.

        Returns:
            Deduplicated ``ArtefactSet`` with computed ``categories_present``.
        """
        merged: list[Artefact] = []
        seen_ids: set[str] = set()
        for result in parser_results:
            for artefact in result.artefacts:
                if artefact.artefact_id in seen_ids:
                    continue
                seen_ids.add(artefact.artefact_id)
                merged.append(artefact)

        categories: list[ArtefactCategory] = sorted(
            {artefact.category for artefact in merged},
            key=lambda item: item.value,
        )
        summary = (
            f"Normalised {len(merged)} artefacts across {len(categories)} categories."
        )
        logger.info(summary)
        return ArtefactSet(
            evidence_id=evidence_id,
            artefacts=merged,
            categories_present=categories,
        )
