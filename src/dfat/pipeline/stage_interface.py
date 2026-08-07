"""Abstract pipeline stage interface and shared stage context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import PipelineStage
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import EvidenceImage
from dfat.core.models.pipeline import StageResult
from dfat.core.models.report import ForensicReport
from dfat.pipeline.models import PipelineJob


class PipelineContext(BaseModel):
    """Mutable context passed between stages, carrying accumulated state.

    Attributes:
        job: Pipeline job being executed.
        evidence: Acquired evidence metadata when available.
        artefact_set: Normalised parsed artefacts.
        ranked_artefacts: Triaged ranked artefacts.
        summary_text: Investigative summary text.
        report: Dual-output forensic report when built.
        stage_timings: Per-stage duration seconds keyed by stage value.
        metadata: Free-form cross-stage metadata bag.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    job: PipelineJob
    evidence: Optional[EvidenceImage] = None
    artefact_set: Optional[ArtefactSet] = None
    ranked_artefacts: Optional[list[RankedArtefact]] = None
    summary_text: Optional[str] = None
    report: Optional[ForensicReport] = None
    stage_timings: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IPipelineStage(ABC):
    """Abstract executable handler for a single ``PipelineStage``."""

    @abstractmethod
    async def execute(self, context: PipelineContext) -> StageResult:
        """Execute this stage against the shared pipeline context.

        Args:
            context: Mutable accumulated pipeline state.

        Returns:
            ``StageResult`` describing success/failure and outputs.
        """

    @property
    @abstractmethod
    def stage_name(self) -> PipelineStage:
        """Return the ``PipelineStage`` this handler implements."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of this stage."""

    @abstractmethod
    async def validate_preconditions(self, context: PipelineContext) -> bool:
        """Return whether the stage may run given the current context.

        Args:
            context: Mutable accumulated pipeline state.

        Returns:
            ``True`` when preconditions are satisfied.
        """
