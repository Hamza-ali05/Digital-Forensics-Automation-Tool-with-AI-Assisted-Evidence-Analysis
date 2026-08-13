"""Reproducibility verification for dual-run forensic JSON reports.

Compares artefact-layer integrity hashes across two pipeline runs on the same
evidence. Report metadata (``report_id``, ``generated_at``) is excluded from
the hash so identical artefact inputs remain reproducible (Scanlon et al., 2023).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import HashAlgorithm
from dfat.shared.hashing import compute_data_hash


class ReproducibilityResult(BaseModel):
    """Outcome of comparing two structured JSON report documents."""

    model_config = ConfigDict(frozen=False)

    is_reproducible: bool
    hash_a: str
    hash_b: str
    hashes_match: bool
    artefact_count_match: bool
    category_distribution_match: bool
    suspicion_distribution_match: bool
    differences: list[str] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReproducibilityVerifier:
    """Verify deterministic reproducibility of structured JSON report outputs."""

    def __init__(
        self,
        hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256,
    ) -> None:
        """Initialise the verifier.

        Args:
            hash_algorithm: Algorithm used to hash canonical artefact JSON
                (must match ``StructuredJSONExporter`` / integrity verifier).
        """
        self._hash_algorithm = hash_algorithm

    def compare_reports(
        self,
        report_a: dict[str, Any],
        report_b: dict[str, Any],
    ) -> ReproducibilityResult:
        """Compare two report documents for artefact-layer reproducibility.

        Args:
            report_a: First structured JSON report document.
            report_b: Second structured JSON report document.

        Returns:
            ``ReproducibilityResult`` with hash comparison, distribution checks,
            and a human-readable difference list when runs diverge.
        """
        verified_at = datetime.now(UTC)
        artefacts_a = self._extract_artefacts(report_a) or []
        artefacts_b = self._extract_artefacts(report_b) or []

        hash_a = self._compute_integrity_hash(artefacts_a)
        hash_b = self._compute_integrity_hash(artefacts_b)
        hashes_match = hash_a.lower() == hash_b.lower()

        count_match = len(artefacts_a) == len(artefacts_b)
        cats_a = self._category_distribution(artefacts_a)
        cats_b = self._category_distribution(artefacts_b)
        sus_a = self._suspicion_distribution(artefacts_a)
        sus_b = self._suspicion_distribution(artefacts_b)
        category_match = cats_a == cats_b
        suspicion_match = sus_a == sus_b

        differences: list[str] = []
        if not hashes_match:
            differences.append(
                f"integrity_hash mismatch: a={hash_a} b={hash_b}"
            )
        if not count_match:
            differences.append(
                f"artefact count mismatch: a={len(artefacts_a)} b={len(artefacts_b)}"
            )
        if not category_match:
            differences.append(
                f"category distribution mismatch: a={dict(cats_a)} b={dict(cats_b)}"
            )
        if not suspicion_match:
            differences.append(
                f"suspicion distribution mismatch: a={dict(sus_a)} b={dict(sus_b)}"
            )
        if not hashes_match:
            differences.extend(self._diff_artefacts(artefacts_a, artefacts_b))

        is_reproducible = (
            hashes_match
            and count_match
            and category_match
            and suspicion_match
            and not differences
        )
        # When hashes match, distributions should match for identical arrays;
        # still require the three distribution flags for the result contract.
        if hashes_match and count_match and category_match and suspicion_match:
            is_reproducible = True
            differences = []

        return ReproducibilityResult(
            is_reproducible=is_reproducible,
            hash_a=hash_a,
            hash_b=hash_b,
            hashes_match=hashes_match,
            artefact_count_match=count_match,
            category_distribution_match=category_match,
            suspicion_distribution_match=suspicion_match,
            differences=differences,
            verified_at=verified_at,
        )

    def verify_determinism(self, report: dict[str, Any]) -> bool:
        """Verify artefact serialisation is deterministic vs stored hash.

        Reserialises ``artefact_data`` / ``artefacts`` with ``sort_keys=True``
        and recomputes the integrity hash. Returns True when it matches the
        stored ``integrity_hash``.

        Args:
            report: Structured JSON report document.

        Returns:
            True when the recomputed hash matches the stored integrity hash.
        """
        artefacts = self._extract_artefacts(report)
        if artefacts is None:
            return False
        stored = str(report.get("integrity_hash") or "").lower()
        if not stored:
            return False
        recomputed = self._compute_integrity_hash(artefacts).lower()
        return stored == recomputed

    def _compute_integrity_hash(self, artefact_data: list[dict[str, Any]]) -> str:
        """Compute the integrity digest over canonical artefact JSON."""
        canonical = json.dumps(
            artefact_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        return compute_data_hash(canonical.encode("utf-8"), self._hash_algorithm)

    @staticmethod
    def _extract_artefacts(
        report_data: dict[str, Any],
    ) -> Optional[list[dict[str, Any]]]:
        """Return the artefact array from schema or domain-model key names."""
        raw = report_data.get("artefacts")
        if raw is None:
            raw = report_data.get("artefact_data")
        if raw is None:
            return None
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    @staticmethod
    def _category_distribution(artefacts: list[dict[str, Any]]) -> Counter[str]:
        """Count artefacts by category."""
        return Counter(str(row.get("category") or "unknown") for row in artefacts)

    @staticmethod
    def _suspicion_distribution(artefacts: list[dict[str, Any]]) -> Counter[str]:
        """Count artefacts by suspicion level."""
        return Counter(
            str(row.get("suspicion_level") or "unknown") for row in artefacts
        )

    def _diff_artefacts(
        self,
        artefacts_a: list[dict[str, Any]],
        artefacts_b: list[dict[str, Any]],
    ) -> list[str]:
        """Produce field-level differences between two artefact arrays."""
        differences: list[str] = []
        index_a = self._index_by_id(artefacts_a)
        index_b = self._index_by_id(artefacts_b)

        only_a = sorted(set(index_a) - set(index_b))
        only_b = sorted(set(index_b) - set(index_a))
        for artefact_id in only_a:
            differences.append(f"artefact only in report A: {artefact_id}")
        for artefact_id in only_b:
            differences.append(f"artefact only in report B: {artefact_id}")

        for artefact_id in sorted(set(index_a) & set(index_b)):
            row_a = index_a[artefact_id]
            row_b = index_b[artefact_id]
            field_diffs = self._diff_fields(row_a, row_b, prefix=artefact_id)
            differences.extend(field_diffs)

        # When IDs are missing/duplicated, fall back to positional comparison.
        if not index_a and not index_b and (artefacts_a or artefacts_b):
            limit = max(len(artefacts_a), len(artefacts_b))
            for idx in range(limit):
                if idx >= len(artefacts_a):
                    differences.append(f"positional artefact [{idx}] only in report B")
                    continue
                if idx >= len(artefacts_b):
                    differences.append(f"positional artefact [{idx}] only in report A")
                    continue
                differences.extend(
                    self._diff_fields(
                        artefacts_a[idx],
                        artefacts_b[idx],
                        prefix=f"index[{idx}]",
                    )
                )

        if not differences:
            differences.append(
                "artefact arrays differ in serialisation order or non-indexed fields"
            )
        return differences

    @staticmethod
    def _index_by_id(
        artefacts: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Index artefacts by ``artefact_id`` (last wins on duplicates)."""
        indexed: dict[str, dict[str, Any]] = {}
        for row in artefacts:
            artefact_id = row.get("artefact_id")
            if isinstance(artefact_id, str) and artefact_id.strip():
                indexed[artefact_id] = row
        return indexed

    @staticmethod
    def _diff_fields(
        row_a: dict[str, Any],
        row_b: dict[str, Any],
        *,
        prefix: str,
    ) -> list[str]:
        """Compare two artefact dicts field-by-field."""
        diffs: list[str] = []
        keys = sorted(set(row_a) | set(row_b))
        for key in keys:
            if key not in row_a:
                diffs.append(f"{prefix}.{key}: missing in report A")
                continue
            if key not in row_b:
                diffs.append(f"{prefix}.{key}: missing in report B")
                continue
            value_a = row_a[key]
            value_b = row_b[key]
            if value_a != value_b:
                # Canonicalise nested structures for a stable message.
                left = json.dumps(value_a, sort_keys=True, default=str)
                right = json.dumps(value_b, sort_keys=True, default=str)
                if left != right:
                    diffs.append(f"{prefix}.{key}: {left} != {right}")
        return diffs
