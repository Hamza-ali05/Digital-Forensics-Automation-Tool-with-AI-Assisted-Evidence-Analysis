"""Pydantic response models for the DFAT REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from dfat.core.enums import EvidenceType


class EvidenceResponse(BaseModel):
    """Evidence metadata response."""

    evidence_id: str
    file_path: str
    evidence_type: EvidenceType
    original_hash: str
    case: dict[str, Any]
    registered_by: Optional[str] = None


class AnalysisStatusResponse(BaseModel):
    """Pipeline analysis status response."""

    pipeline_id: str
    current_stage: str
    is_complete: bool
    stage_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ReportResponse(BaseModel):
    """Forensic report summary response."""

    report_id: str
    case_name: str
    json_report_url: str
    narrative_report_url: str
    generated_at: datetime
    pipeline_duration_seconds: float


class IntegrityVerifyResponse(BaseModel):
    """Report integrity verification outcome."""

    is_valid: bool
    integrity_hash_match: bool
    schema_version_valid: bool
    report_id_valid: bool
    issues: list[str] = Field(default_factory=list)
    verified_at: datetime


class ReproducibilityCompareResponse(BaseModel):
    """Reproducibility comparison of two reports."""

    is_reproducible: bool
    hash_a: str
    hash_b: str
    hashes_match: bool
    artefact_count_match: bool
    category_distribution_match: bool
    suspicion_distribution_match: bool
    differences: list[str] = Field(default_factory=list)
    verified_at: datetime


class BenchmarkResponse(BaseModel):
    """Benchmark evaluation response."""

    benchmark_id: str
    dataset_name: str = ""
    precision: float
    recall: float
    f1_score: float
    time_to_triage_seconds: float
    artefacts_expected: int
    artefacts_recovered: int
    false_positives: int = 0
    false_negatives: int = 0
    evaluated_at: Optional[datetime] = None


class DatasetListResponse(BaseModel):
    """Available local ground-truth datasets."""

    dfrws: list[str] = Field(default_factory=list)
    cfreds: list[str] = Field(default_factory=list)


class UsabilitySubmitResponse(BaseModel):
    """Acknowledgement of an anonymised usability submission."""

    participant_id: str
    message: str = "Response collected anonymously."


class UsabilityDeleteResponse(BaseModel):
    """Ethics data-destruction acknowledgement."""

    deleted_count: int


class ErrorResponse(BaseModel):
    """Standard API error response."""

    error_type: str
    message: str
    timestamp: datetime
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None


class ParserInfoResponse(BaseModel):
    """Single artefact parser availability entry."""

    parser_name: str
    available: bool
    supported_evidence_types: list[str] = Field(default_factory=list)


class ParserListResponse(BaseModel):
    """List of registered artefact parsers."""

    parsers: list[ParserInfoResponse] = Field(default_factory=list)
    total: int = 0
