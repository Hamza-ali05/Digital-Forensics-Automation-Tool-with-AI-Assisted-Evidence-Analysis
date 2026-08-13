"""Deterministic structured JSON artefact exporter (primary evidential record).

The integrity hash covers only the serialised ``artefacts`` array. Report
metadata (``report_id``, ``generated_at``) is excluded so identical artefact
inputs produce identical hashes across runs (Scanlon et al., 2023).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from dfat.ai_engine.llm.config import PROMPT_VERSION
from dfat.core.enums import ArtefactCategory, HashAlgorithm, SuspicionLevel
from dfat.core.exceptions import JSONSchemaValidationError
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import JSONReport
from dfat.reporting.schema import ReportSchemaValidator
from dfat.shared.constants import JSON_SCHEMA_VERSION
from dfat.shared.hashing import compute_data_hash

_TIMING_KEYS = (
    "acquisition_seconds",
    "parsing_seconds",
    "triage_seconds",
    "reporting_seconds",
)

_DEFAULT_AI_DISCLAIMER = (
    "AI-generated investigative content is advisory. The structured JSON "
    "artefact layer is the authoritative evidential record "
    "(Scanlon et al., 2023)."
)


class StructuredJSONExporter:
    """Export ranked artefacts to a schema-validated JSON report."""

    def __init__(
        self,
        schema_validator: ReportSchemaValidator,
        hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256,
    ) -> None:
        """Initialise the exporter.

        Args:
            schema_validator: Report schema validator (Prompt 6.1).
            hash_algorithm: Algorithm for artefact integrity hashing.
        """
        self._validator = schema_validator
        self._hash_algorithm = hash_algorithm

    def export(
        self,
        artefact_set: ArtefactSet,
        ranked_artefacts: list[RankedArtefact],
        case: CaseMetadata,
        stage_timings: dict[str, float],
        ai_metadata: Optional[dict[str, Any]] = None,
        evidence_hash: str = "",
    ) -> JSONReport:
        """Build, hash, validate, and return a structured JSON report.

        Args:
            artefact_set: Source artefact set (provides ``evidence_id``).
            ranked_artefacts: Triaged artefacts for the evidential array.
            case: Case metadata for the report envelope.
            stage_timings: Pipeline stage timings in seconds.
            ai_metadata: Optional AI analysis metadata block.
            evidence_hash: Hash of the input evidence image/file.

        Returns:
            Validated ``JSONReport`` domain model.

        Raises:
            JSONSchemaValidationError: If schema validation fails.
        """
        artefact_data = self._serialise_artefacts(ranked_artefacts)
        integrity_hash = self._compute_integrity_hash(artefact_data)
        report_id = str(uuid4())
        generated_at = datetime.now(UTC)
        timings = self._normalise_timings(stage_timings)
        summary_statistics = self._compute_summary_statistics(ranked_artefacts)
        ai_block = self._normalise_ai_metadata(ai_metadata)

        document: dict[str, Any] = {
            "schema_version": JSON_SCHEMA_VERSION,
            "report_id": report_id,
            "evidence_id": artefact_set.evidence_id,
            "case_metadata": {
                "case_id": case.case_id,
                "case_name": case.case_name,
                "investigator": case.investigator,
            },
            "generated_at": generated_at.isoformat(),
            "integrity_hash": integrity_hash,
            "pipeline_stage_timings": timings,
            "artefacts": artefact_data,
            "summary_statistics": summary_statistics,
            "ai_metadata": ai_block,
            "reproducibility": {
                "artefact_data_hash": integrity_hash,
                "input_evidence_hash": evidence_hash or "",
                "tool_version": self._tool_version(),
                "schema_version": JSON_SCHEMA_VERSION,
            },
        }
        self.validate_against_schema(document)

        return JSONReport(
            report_id=report_id,
            evidence_id=artefact_set.evidence_id,
            artefact_data=artefact_data,
            schema_version=JSON_SCHEMA_VERSION,
            generated_at=generated_at,
            integrity_hash=integrity_hash,
        )

    def validate_against_schema(self, json_data: dict[str, Any]) -> bool:
        """Validate a document against the report JSON Schema.

        Args:
            json_data: Candidate report document.

        Returns:
            True when valid.

        Raises:
            JSONSchemaValidationError: When validation fails.
        """
        result = self._validator.validate(json_data)
        if not result.is_valid:
            raise JSONSchemaValidationError(
                "JSON report failed schema validation",
                validation_errors=list(result.errors),
            )
        return True

    def _compute_summary_statistics(
        self,
        ranked: list[RankedArtefact],
    ) -> dict[str, Any]:
        """Count artefacts by category and suspicion level.

        Args:
            ranked: Ranked artefacts.

        Returns:
            Summary statistics mapping with zeros for all enum members.
        """
        by_category = {category.value: 0 for category in ArtefactCategory}
        by_suspicion = {level.value: 0 for level in SuspicionLevel}
        for artefact in ranked:
            by_category[artefact.category.value] = (
                by_category.get(artefact.category.value, 0) + 1
            )
            by_suspicion[artefact.suspicion_level.value] = (
                by_suspicion.get(artefact.suspicion_level.value, 0) + 1
            )
        return {
            "total_artefacts": len(ranked),
            "by_category": by_category,
            "by_suspicion_level": by_suspicion,
        }

    def _serialise_artefacts(
        self,
        ranked_artefacts: list[RankedArtefact],
    ) -> list[dict[str, Any]]:
        """Serialise ranked artefacts in a deterministic order.

        Args:
            ranked_artefacts: Triaged artefacts.

        Returns:
            Sorted list of artefact dictionaries (no volatile fields).
        """
        rows: list[dict[str, Any]] = []
        for artefact in ranked_artefacts:
            rows.append(
                {
                    "artefact_id": artefact.artefact_id,
                    "category": artefact.category.value,
                    "source_path": artefact.source_path,
                    "suspicion_level": artefact.suspicion_level.value,
                    "relevance_score": artefact.relevance_score,
                    "raw_data": artefact.raw_data,
                    "classification_reasoning": artefact.classification_reasoning,
                    "metadata": dict(artefact.metadata),
                }
            )
        return self._sort_artefacts_deterministically(rows)

    @staticmethod
    def _sort_artefacts_deterministically(
        artefacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Sort artefact dicts by ``(category, artefact_id)``."""
        return sorted(
            artefacts,
            key=lambda row: (
                str(row.get("category", "")),
                str(row.get("artefact_id", "")),
            ),
        )

    def _compute_integrity_hash(self, artefact_data: list[dict[str, Any]]) -> str:
        """Compute SHA-256 over canonical JSON of the artefact array only.

        Args:
            artefact_data: Deterministically ordered artefact dictionaries.

        Returns:
            Hexadecimal integrity digest (never includes report metadata).
        """
        canonical = json.dumps(
            artefact_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        return compute_data_hash(canonical.encode("utf-8"), self._hash_algorithm)

    @staticmethod
    def _normalise_timings(stage_timings: dict[str, float]) -> dict[str, float]:
        """Ensure required timing keys are present (``*_seconds`` names).

        Args:
            stage_timings: Caller-provided timings.

        Returns:
            Timing map with required keys defaulting to 0.0.
        """
        aliases = {
            "acquisition": "acquisition_seconds",
            "acquisition_s": "acquisition_seconds",
            "acquisition_seconds": "acquisition_seconds",
            "parsing": "parsing_seconds",
            "parsing_s": "parsing_seconds",
            "parsing_seconds": "parsing_seconds",
            "triage": "triage_seconds",
            "triage_s": "triage_seconds",
            "ai_triage": "triage_seconds",
            "triage_seconds": "triage_seconds",
            "reporting": "reporting_seconds",
            "reporting_s": "reporting_seconds",
            "reporting_seconds": "reporting_seconds",
        }
        normalised = {key: 0.0 for key in _TIMING_KEYS}
        for key, value in stage_timings.items():
            target = aliases.get(key, key)
            if target in normalised:
                normalised[target] = float(value)
        return normalised

    @staticmethod
    def _normalise_ai_metadata(
        ai_metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a complete ``ai_metadata`` block with safe defaults."""
        defaults: dict[str, Any] = {
            "model_used": "none",
            "prompt_version": PROMPT_VERSION,
            "confidence_score": 0.0,
            "analysis_mode": "rule_based",
            "disclaimer": _DEFAULT_AI_DISCLAIMER,
        }
        if not ai_metadata:
            return defaults
        merged = dict(defaults)
        for key in defaults:
            if key in ai_metadata and ai_metadata[key] is not None:
                merged[key] = ai_metadata[key]
        return merged

    @staticmethod
    def _tool_version() -> str:
        """Return the DFAT package version for reproducibility metadata."""
        try:
            from dfat import __version__

            return str(__version__)
        except Exception:  # noqa: BLE001
            return "0.0.0"
