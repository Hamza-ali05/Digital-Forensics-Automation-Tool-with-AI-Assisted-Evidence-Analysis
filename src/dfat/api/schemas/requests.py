"""Pydantic request models for the DFAT REST API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from dfat.core.enums import EvidenceType


class EvidenceUploadRequest(BaseModel):
    """Request body for registering forensic evidence."""

    file_path: str
    case_name: str
    investigator: str
    description: Optional[str] = None
    evidence_type: EvidenceType


class AnalysisRunRequest(BaseModel):
    """Request body for starting a pipeline analysis run."""

    evidence_id: str
    mode: str = Field(default="full", pattern="^(full|parse-only|triage-only)$")
    use_fallback: bool = False


class PipelineRunRequest(BaseModel):
    """Request body for submitting a pipeline job."""

    evidence_id: str
    case_id: str
    mode: str = Field(default="full", pattern="^(full|parse-only|triage-only)$")
    use_fallback: bool = False


class BenchmarkRunRequest(BaseModel):
    """Request body for running a benchmark evaluation."""

    evidence_id: str
    ground_truth_dataset: str = ""
    dataset_source: Literal["dfrws", "cfreds"] = "dfrws"
    # Legacy fields retained for older clients / tests.
    ground_truth_path: Optional[str] = None
    dataset_name: Optional[str] = None


class ReportCompareRequest(BaseModel):
    """Request body for reproducibility comparison of two reports."""

    report_id_a: str
    report_id_b: str


class UsabilityRespondRequest(BaseModel):
    """Anonymous usability questionnaire submission body."""

    ratings: dict[str, int] = Field(default_factory=dict)
    free_text: Optional[str] = None
