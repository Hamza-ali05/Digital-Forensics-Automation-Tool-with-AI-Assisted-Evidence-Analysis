"""Classification result model shared by parser and classifier."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import SuspicionLevel


class ClassificationResult(BaseModel):
    """Structured classification outcome for a single artefact."""

    model_config = ConfigDict(frozen=False)

    artefact_id: str
    suspicion_level: SuspicionLevel
    reasoning: str
    ioc_indicators: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    raw_llm_response: Optional[str] = None
