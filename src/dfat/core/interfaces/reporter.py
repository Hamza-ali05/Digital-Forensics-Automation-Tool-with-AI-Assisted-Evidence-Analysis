"""Abstract report generator port for reporting engine implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

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
    ) -> JSONReport:
        """Generate the machine-readable JSON report layer.

        Args:
            artefact_set: Parsed artefact collection.
            ranked: Triaged ranked artefacts.

        Returns:
            Structured JSON report.
        """

    @abstractmethod
    def generate_narrative_report(
        self,
        summary: str,
        llm_model: str,
        params: dict[str, Any],
    ) -> NarrativeReport:
        """Generate the human-readable narrative report.

        Args:
            summary: Investigative summary text.
            llm_model: Local model identifier used for generation.
            params: Generation parameter snapshot.

        Returns:
            Narrative report artefact.
        """

    @abstractmethod
    def generate_full_report(
        self,
        case: CaseMetadata,
        json_report: JSONReport,
        narrative: NarrativeReport,
        duration: float,
        timings: dict[str, float],
    ) -> ForensicReport:
        """Combine JSON and narrative outputs into a full forensic report.

        Args:
            case: Case metadata associated with the report.
            json_report: Machine-readable report component.
            narrative: Human-readable report component.
            duration: End-to-end pipeline duration in seconds.
            timings: Per-stage timing map in seconds.

        Returns:
            Combined dual-output forensic report.
        """
