"""Dual-output forensic report domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.models.evidence import CaseMetadata


class JSONReport(BaseModel):
    """Machine-readable structured JSON forensic report.

    Attributes:
        report_id: Unique report identifier.
        evidence_id: Source evidence identifier.
        artefact_data: Serialised artefact records.
        schema_version: JSON artefact schema version.
        generated_at: UTC generation timestamp.
        integrity_hash: Hash of the structured artefact payload.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    evidence_id: str
    artefact_data: list[dict[str, Any]] = Field(default_factory=list)
    schema_version: str = "1.0.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    integrity_hash: str


class NarrativeReport(BaseModel):
    """Human-readable investigative narrative report.

    Attributes:
        report_id: Unique report identifier.
        evidence_id: Source evidence identifier.
        summary_text: Narrative investigative summary.
        llm_model_used: Local model identifier used for generation.
        generation_parameters: Model/generation parameter snapshot.
        generated_at: UTC generation timestamp.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    evidence_id: str
    summary_text: str
    llm_model_used: str
    generation_parameters: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ForensicReport(BaseModel):
    """Combined dual-output forensic report for a case.

    Attributes:
        report_id: Unique combined report identifier.
        case: Associated case metadata.
        json_report: Machine-readable JSON component.
        narrative_report: Human-readable narrative component.
        pipeline_duration_seconds: End-to-end pipeline duration.
        stage_timings: Per-stage duration map in seconds.
        audit_metadata: Generation audit metadata embedded at report time.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    case: CaseMetadata
    json_report: JSONReport
    narrative_report: NarrativeReport
    pipeline_duration_seconds: float
    stage_timings: dict[str, float] = Field(default_factory=dict)
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
