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


class BenchmarkResponse(BaseModel):
    """Benchmark evaluation response."""

    benchmark_id: str
    precision: float
    recall: float
    f1_score: float
    time_to_triage_seconds: float
    artefacts_expected: int
    artefacts_recovered: int


class ErrorResponse(BaseModel):
    """Standard API error response."""

    error_type: str
    message: str
    timestamp: datetime
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None
