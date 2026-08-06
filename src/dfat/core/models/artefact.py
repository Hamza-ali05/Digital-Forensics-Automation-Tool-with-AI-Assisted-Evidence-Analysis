"""Artefact domain models for parsed and triaged forensic findings."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.core.enums import ArtefactCategory, SuspicionLevel


class Artefact(BaseModel):
    """A single extracted forensic artefact.

    Attributes:
        artefact_id: Unique artefact identifier.
        category: Artefact category taxonomy value.
        source_evidence_id: Identifier of the source evidence item.
        raw_data: Parser-produced structured payload.
        parsed_at: UTC timestamp when the artefact was parsed.
        source_path: Optional path or location within the evidence.
        metadata: Additional unstructured metadata.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    artefact_id: str = Field(default_factory=lambda: str(uuid4()))
    category: ArtefactCategory
    source_evidence_id: str
    raw_data: dict[str, Any]
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RankedArtefact(Artefact):
    """Artefact enriched with AI triage ranking and suspicion classification.

    Attributes:
        suspicion_level: Assigned suspicion classification.
        relevance_score: Relevance score in the closed interval [0.0, 1.0].
        classification_reasoning: Optional explanation from the triage model.
    """

    suspicion_level: SuspicionLevel
    relevance_score: float = Field(ge=0.0, le=1.0)
    classification_reasoning: Optional[str] = None


class ArtefactSet(BaseModel):
    """Collection of artefacts extracted from a single evidence item.

    Attributes:
        evidence_id: Source evidence identifier.
        artefacts: Extracted artefact list.
        categories_present: Distinct categories represented in ``artefacts``.
        extraction_timestamp: UTC timestamp of extraction completion.
        total_count: Computed count of artefacts in the set.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    evidence_id: str
    artefacts: list[Artefact] = Field(default_factory=list)
    categories_present: list[ArtefactCategory] = Field(default_factory=list)
    extraction_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_count(self) -> int:
        """Return the number of artefacts in the set."""
        return len(self.artefacts)
