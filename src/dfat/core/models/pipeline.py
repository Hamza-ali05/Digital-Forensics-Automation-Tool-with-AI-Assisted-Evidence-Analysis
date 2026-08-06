"""Pipeline state and audit trail domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.core.enums import PipelineStage
from dfat.core.models.evidence import CaseMetadata

_REQUIRED_STAGES: frozenset[str] = frozenset(stage.value for stage in PipelineStage)


class AuditEntry(BaseModel):
    """ACPO-oriented audit trail entry for a pipeline action.

    Attributes:
        entry_number: Sequential audit entry number.
        timestamp: UTC timestamp of the action.
        stage: Pipeline stage associated with the action.
        action: Short action description.
        evidence_id: Related evidence identifier.
        hash_before: Optional evidence/output hash before the action.
        hash_after: Optional evidence/output hash after the action.
        details: Additional structured audit details.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    entry_number: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stage: PipelineStage
    action: str
    evidence_id: str
    hash_before: Optional[str] = None
    hash_after: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class StageResult(BaseModel):
    """Outcome of a single pipeline stage execution.

    Attributes:
        stage: Pipeline stage that produced this result.
        success: Whether the stage completed successfully.
        duration_seconds: Stage wall-clock duration in seconds.
        output_data: Stage-specific output payload.
        errors: Collected error messages for the stage.
        audit_entries: Audit entries recorded during the stage.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    stage: PipelineStage
    success: bool
    duration_seconds: float
    output_data: Any = None
    errors: list[str] = Field(default_factory=list)
    audit_entries: list[AuditEntry] = Field(default_factory=list)


class PipelineState(BaseModel):
    """Mutable state for an end-to-end forensic pipeline run.

    Attributes:
        pipeline_id: Unique pipeline run identifier.
        case: Associated case metadata.
        current_stage: Stage currently executing or last reached.
        stage_results: Mapping of stage name to stage result.
        started_at: UTC pipeline start timestamp.
        completed_at: Optional UTC completion timestamp.
        is_complete: Whether results exist for all five pipeline stages.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    pipeline_id: str = Field(default_factory=lambda: str(uuid4()))
    case: CaseMetadata
    current_stage: PipelineStage
    stage_results: dict[str, StageResult] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_complete(self) -> bool:
        """Return True when all five pipeline stages have results."""
        return _REQUIRED_STAGES.issubset(self.stage_results.keys())
