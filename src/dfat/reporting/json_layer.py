"""Deterministic structured JSON artefact exporter (primary evidential record).

The integrity hash covers only the serialised ``artefacts`` array. Report
metadata (``report_id``, ``generated_at``) is excluded so identical artefact
inputs produce identical hashes across runs (Scanlon et al., 2023).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import jsonschema

from dfat.core.enums import HashAlgorithm
from dfat.core.exceptions import JSONSchemaValidationError
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import JSONReport
from dfat.shared.constants import JSON_SCHEMA_VERSION
from dfat.shared.hashing import compute_data_hash

_TIMING_KEYS = ("acquisition_s", "parsing_s", "triage_s", "reporting_s")


class StructuredJSONExporter:
    """Export ranked artefacts to a schema-validated JSON report."""

    def __init__(
        self,
        schema_path: Path,
        hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256,
    ) -> None:
        """Initialise the exporter.

        Args:
            schema_path: Path to ``report_schema.json``.
            hash_algorithm: Algorithm for artefact integrity hashing.
        """
        self._schema_path = schema_path
        self._hash_algorithm = hash_algorithm
        with schema_path.open("r", encoding="utf-8") as handle:
            self._schema: dict[str, Any] = json.load(handle)

    def export(
        self,
        artefact_set: ArtefactSet,
        ranked_artefacts: list[RankedArtefact],
        case: CaseMetadata,
        stage_timings: dict[str, float],
    ) -> JSONReport:
        """Build, hash, validate, and return a structured JSON report.

        Args:
            artefact_set: Source artefact set (provides ``evidence_id``).
            ranked_artefacts: Triaged artefacts for the evidential array.
            case: Case metadata for the report envelope.
            stage_timings: Pipeline stage timings in seconds.

        Returns:
            Validated ``JSONReport`` domain model.

        Raises:
            JSONSchemaValidationError: If schema validation fails.
        """
        artefact_data = self._serialise_artefacts(ranked_artefacts)
        integrity_hash = self._hash_artefact_data(artefact_data)
        report_id = str(uuid4())
        generated_at = datetime.now(UTC)
        timings = self._normalise_timings(stage_timings)
        summary_statistics = self._compute_summary_statistics(ranked_artefacts)

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
        validator = jsonschema.Draft7Validator(
            self._schema,
            format_checker=jsonschema.FormatChecker(),
        )
        errors = sorted(validator.iter_errors(json_data), key=lambda err: list(err.path))
        if errors:
            messages = [f"{'/'.join(str(p) for p in err.path)}: {err.message}" for err in errors]
            raise JSONSchemaValidationError(
                "JSON report failed schema validation",
                validation_errors=messages,
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
            Summary statistics mapping.
        """
        by_category: dict[str, int] = {}
        by_suspicion: dict[str, int] = {}
        for artefact in ranked:
            by_category[artefact.category.value] = (
                by_category.get(artefact.category.value, 0) + 1
            )
            by_suspicion[artefact.suspicion_level.value] = (
                by_suspicion.get(artefact.suspicion_level.value, 0) + 1
            )
        return {
            "total_artefacts": len(ranked),
            "by_category": dict(sorted(by_category.items())),
            "by_suspicion_level": dict(sorted(by_suspicion.items())),
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
                }
            )
        rows.sort(key=lambda row: row["artefact_id"])
        return rows

    def _hash_artefact_data(self, artefact_data: list[dict[str, Any]]) -> str:
        """Compute SHA-256 over canonical JSON of the artefact array.

        Args:
            artefact_data: Deterministically ordered artefact dictionaries.

        Returns:
            Hexadecimal integrity digest.
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
        """Ensure required timing keys are present.

        Args:
            stage_timings: Caller-provided timings.

        Returns:
            Timing map with required keys defaulting to 0.0.
        """
        aliases = {
            "acquisition": "acquisition_s",
            "parsing": "parsing_s",
            "triage": "triage_s",
            "ai_triage": "triage_s",
            "reporting": "reporting_s",
        }
        normalised = {key: 0.0 for key in _TIMING_KEYS}
        for key, value in stage_timings.items():
            target = aliases.get(key, key)
            if target in normalised:
                normalised[target] = float(value)
        return normalised
