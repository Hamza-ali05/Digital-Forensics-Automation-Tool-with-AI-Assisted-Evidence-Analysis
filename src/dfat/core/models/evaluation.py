"""Benchmark and usability evaluation domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class BenchmarkResult(BaseModel):
    """Result of comparing pipeline output against ground truth.

    Attributes:
        benchmark_id: Unique benchmark run identifier.
        dataset_name: Ground-truth dataset name (e.g., DFRWS/CFReDS).
        precision: Precision score.
        recall: Recall score.
        f1_score: F1 score.
        time_to_triage_seconds: Measured time-to-triage.
        artefacts_expected: Expected relevant artefact count.
        artefacts_recovered: Recovered relevant artefact count.
        false_positives: False positive count.
        false_negatives: False negative count.
        evaluated_at: UTC evaluation timestamp.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    benchmark_id: str = Field(default_factory=lambda: str(uuid4()))
    dataset_name: str
    precision: float
    recall: float
    f1_score: float
    time_to_triage_seconds: float
    artefacts_expected: int
    artefacts_recovered: int
    false_positives: int
    false_negatives: int
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UsabilityResponse(BaseModel):
    """Anonymised usability questionnaire response.

    Attributes:
        response_id: Unique response identifier.
        participant_id: Anonymised participant identifier.
        usefulness_rating: Usefulness rating on a 1–5 scale.
        accuracy_rating: Accuracy rating on a 1–5 scale.
        clarity_rating: Clarity rating on a 1–5 scale.
        free_text_feedback: Optional free-text comments.
        submitted_at: UTC submission timestamp.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    response_id: str = Field(default_factory=lambda: str(uuid4()))
    participant_id: str
    usefulness_rating: int = Field(ge=1, le=5)
    accuracy_rating: int = Field(ge=1, le=5)
    clarity_rating: int = Field(ge=1, le=5)
    free_text_feedback: Optional[str] = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
