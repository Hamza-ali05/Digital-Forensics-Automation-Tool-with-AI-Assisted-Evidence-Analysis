"""Artefact deduplication — content-hash based duplicate removal."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet

logger = logging.getLogger(__name__)


class ArtefactDeduplicator:
    """Remove duplicate artefacts that share the same content fingerprint."""

    def deduplicate(self, artefact_set: ArtefactSet) -> ArtefactSet:
        """Drop artefacts with identical category + ``raw_data`` content hashes.

        Keeps the first occurrence of each content hash. Logs how many
        duplicates were removed. ``ArtefactSet.total_count`` updates via the
        computed field on the returned set.

        Args:
            artefact_set: Standardised (or raw) artefact collection.

        Returns:
            Deduplicated ``ArtefactSet`` with refreshed ``categories_present``.
        """
        unique: list[Artefact] = []
        seen: set[str] = set()
        duplicates_removed = 0

        for artefact in artefact_set.artefacts:
            content_hash = self.content_hash(artefact)
            if content_hash in seen:
                duplicates_removed += 1
                continue
            seen.add(content_hash)
            unique.append(artefact)

        if duplicates_removed:
            logger.info(
                "Removed %d duplicate artefact(s) from evidence %s "
                "(%d → %d)",
                duplicates_removed,
                artefact_set.evidence_id,
                len(artefact_set.artefacts),
                len(unique),
            )
        else:
            logger.debug(
                "No duplicate artefacts found for evidence %s (%d artefacts)",
                artefact_set.evidence_id,
                len(unique),
            )

        categories = sorted({item.category for item in unique}, key=lambda c: c.value)
        return artefact_set.model_copy(
            update={
                "artefacts": unique,
                "categories_present": categories,
            }
        )

    def content_hash(self, artefact: Artefact) -> str:
        """Compute a stable SHA-256 hash of category + sorted ``raw_data``.

        Args:
            artefact: Artefact whose content fingerprint is required.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        payload = {
            "category": artefact.category.value,
            "raw_data": self._canonical(artefact.raw_data),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _canonical(self, value: Any) -> Any:
        """Return a JSON-serialisable, order-stable representation of ``value``."""
        if isinstance(value, dict):
            return {
                str(key): self._canonical(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [self._canonical(item) for item in value]
        if isinstance(value, set):
            return sorted(self._canonical(item) for item in value)
        if isinstance(value, ArtefactCategory):
            return value.value
        if isinstance(value, bytes):
            return value.hex()
        return value
