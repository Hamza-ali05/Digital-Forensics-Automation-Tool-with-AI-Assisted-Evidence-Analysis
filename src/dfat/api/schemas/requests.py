"""Pydantic request models for the DFAT REST API."""

from __future__ import annotations

from typing import Optional

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


class BenchmarkRunRequest(BaseModel):
    """Request body for running a benchmark evaluation."""

    evidence_id: str
    ground_truth_path: str
    dataset_name: str
