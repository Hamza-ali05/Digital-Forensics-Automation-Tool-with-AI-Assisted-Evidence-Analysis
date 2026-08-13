"""Abstract report generator port for reporting engine implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport


class IReportGenerator(ABC):
    """Port for dual-output forensic report generation."""

    @abstractmethod
    def generate_json_report(
        self,
        artefact_set: ArtefactSet,
        ranked: list[RankedArtefact],
        case: CaseMetadata,
        timings: dict[str, float],
        ai_metadata: Optional[dict[str, Any]] = None,
        evidence_hash: str = "",
    ) -> JSONReport:
        """Generate the machine-readable JSON report layer.

        Args:
            artefact_set: Parsed artefact collection.
            ranked: Triaged ranked artefacts.
            case: Case metadata for the report envelope.
            timings: Pipeline stage timings in seconds.
            ai_metadata: Optional AI analysis metadata block.
            evidence_hash: Hash of the input evidence image/file.

        Returns:
            Structured JSON report.
        """

    @abstractmethod
    def generate_narrative_report(
        self,
        summary_result: Any,
        llm_model: str,
        params: dict[str, Any],
        ranked: list[RankedArtefact],
        case: CaseMetadata,
        confidence: float,
    ) -> NarrativeReport:
        """Generate the human-readable narrative report.

        Args:
            summary_result: Structured summary (``SummaryResult``) from the
                AI summarization layer.
            llm_model: Local model identifier used for generation.
            params: Generation parameter snapshot.
            ranked: Triaged ranked artefacts for statistics/findings.
            case: Case metadata for the narrative header.
            confidence: Narrative confidence score in ``[0.0, 1.0]``.

        Returns:
            Narrative report artefact.
        """

    @abstractmethod
    def generate_full_report(
        self,
        case: CaseMetadata,
        json_report: JSONReport,
        narrative_report: NarrativeReport,
        duration: float,
        timings: dict[str, float],
    ) -> ForensicReport:
        """Combine JSON and narrative outputs into a full forensic report.

        Args:
            case: Case metadata associated with the report.
            json_report: Machine-readable report component.
            narrative_report: Human-readable report component.
            duration: End-to-end pipeline duration in seconds.
            timings: Per-stage timing map in seconds.

        Returns:
            Combined dual-output forensic report.
        """
