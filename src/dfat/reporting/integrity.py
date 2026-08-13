"""Report integrity verification and audit metadata embedding.

The integrity hash covers only the serialised artefact array (same
canonicalisation as ``StructuredJSONExporter``), never report metadata
such as ``report_id`` or ``generated_at`` (Scanlon et al., 2023).
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import HashAlgorithm
from dfat.reporting.schema.schema_versions import SCHEMA_REGISTRY, get_latest_version
from dfat.shared.constants import JSON_SCHEMA_VERSION
from dfat.shared.hashing import compute_data_hash


class IntegrityVerificationResult(BaseModel):
    """Outcome of verifying a structured JSON report's integrity."""

    model_config = ConfigDict(frozen=False)

    is_valid: bool
    integrity_hash_match: bool
    schema_version_valid: bool
    report_id_valid: bool
    issues: list[str] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReportIntegrityVerifier:
    """Verify report integrity hashes and embed generation audit metadata."""

    def __init__(
        self,
        hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256,
    ) -> None:
        """Initialise the verifier.

        Args:
            hash_algorithm: Algorithm used to recompute the artefact integrity
                hash (must match the exporter that produced the report).
        """
        self._hash_algorithm = hash_algorithm

    def verify_report(self, report_data: dict[str, Any]) -> IntegrityVerificationResult:
        """Verify that a report document has not been tampered with.

        Args:
            report_data: Loaded structured JSON report document.

        Returns:
            Structured verification outcome with per-check flags and issues.
        """
        issues: list[str] = []
        verified_at = datetime.now(UTC)

        artefacts = self._extract_artefacts(report_data)
        stored_hash = str(report_data.get("integrity_hash") or "")
        if artefacts is None:
            issues.append("Missing artefacts / artefact_data array in report")
            integrity_hash_match = False
        else:
            recomputed = self._compute_integrity_hash(artefacts)
            integrity_hash_match = (
                bool(stored_hash) and stored_hash.lower() == recomputed.lower()
            )
            if not stored_hash:
                issues.append("Missing integrity_hash in report")
            elif not integrity_hash_match:
                issues.append(
                    "integrity_hash does not match recomputed hash of artefact data"
                )

        schema_version = str(report_data.get("schema_version") or "")
        schema_version_valid = self._is_schema_version_valid(schema_version)
        if not schema_version:
            issues.append("Missing schema_version in report")
        elif not schema_version_valid:
            issues.append(
                f"Unsupported schema_version '{schema_version}' "
                f"(expected {get_latest_version()})"
            )

        report_id = report_data.get("report_id")
        report_id_valid = self._is_valid_uuid(report_id)
        if report_id is None or report_id == "":
            issues.append("Missing report_id in report")
        elif not report_id_valid:
            issues.append(f"report_id is not a valid UUID: {report_id!r}")

        is_valid = integrity_hash_match and schema_version_valid and report_id_valid
        return IntegrityVerificationResult(
            is_valid=is_valid,
            integrity_hash_match=integrity_hash_match,
            schema_version_valid=schema_version_valid,
            report_id_valid=report_id_valid,
            issues=issues,
            verified_at=verified_at,
        )

    def verify_report_file(self, report_path: Path) -> IntegrityVerificationResult:
        """Load a JSON report file and verify its integrity.

        Args:
            report_path: Path to a structured JSON report on disk.

        Returns:
            Structured verification outcome.

        Raises:
            FileNotFoundError: If ``report_path`` does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
            TypeError: If the root JSON value is not an object.
        """
        with report_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise TypeError(
                f"Report at {report_path} must be a JSON object, "
                f"got {type(loaded).__name__}"
            )
        return self.verify_report(loaded)

    def embed_audit_metadata(
        self,
        report_data: dict[str, Any],
        user_id: str,
        pipeline_job_id: str,
        evidence_custody_chain_length: int,
        tool_version: str,
    ) -> dict[str, Any]:
        """Return a copy of the report with an ``audit_metadata`` section.

        Args:
            report_data: Source report document.
            user_id: Identifier of the user who generated the report.
            pipeline_job_id: Pipeline job that produced the report.
            evidence_custody_chain_length: Number of custody-chain entries.
            tool_version: DFAT / tool version string.

        Returns:
            Shallow copy of ``report_data`` including ``audit_metadata``.
        """
        audit_metadata = {
            "generated_by_user_id": user_id,
            "pipeline_job_id": pipeline_job_id,
            "custody_chain_entries": evidence_custody_chain_length,
            "tool_version": tool_version,
            "generation_host": socket.gethostname(),
            "generation_timestamp": datetime.now(UTC).isoformat(),
        }
        return {**report_data, "audit_metadata": audit_metadata}

    def _compute_integrity_hash(self, artefact_data: list[dict[str, Any]]) -> str:
        """Compute the integrity digest over canonical artefact JSON.

        Args:
            artefact_data: Artefact dictionaries (order as stored in the report).

        Returns:
            Hexadecimal digest matching ``StructuredJSONExporter``.
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
    def _extract_artefacts(
        report_data: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
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
    def _is_schema_version_valid(schema_version: str) -> bool:
        """Return True when the schema version is registered / current."""
        if not schema_version:
            return False
        if schema_version in SCHEMA_REGISTRY:
            return True
        return schema_version == JSON_SCHEMA_VERSION

    @staticmethod
    def _is_valid_uuid(value: Any) -> bool:
        """Return True when ``value`` is a UUID string or UUID instance."""
        if isinstance(value, UUID):
            return True
        if not isinstance(value, str) or not value:
            return False
        try:
            UUID(value)
        except (ValueError, AttributeError, TypeError):
            return False
        return True
