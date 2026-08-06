"""Abstract AI analyser port for triage engine implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from dfat.core.models.artefact import ArtefactSet, RankedArtefact


class IArtefactAnalyzer(ABC):
    """Port for AI-assisted artefact triage and summarisation."""

    @abstractmethod
    def analyze(self, artefact_set: ArtefactSet) -> list[RankedArtefact]:
        """Classify and rank artefacts by investigative relevance.

        Args:
            artefact_set: Parsed artefacts pending triage.

        Returns:
            Ranked artefacts with suspicion levels and scores.
        """

    @abstractmethod
    def summarize(self, ranked_artefacts: list[RankedArtefact]) -> str:
        """Generate an investigative narrative summary.

        Args:
            ranked_artefacts: Triaged artefacts to summarise.

        Returns:
            Human-readable investigative summary text.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the local LLM endpoint is reachable."""

    @property
    @abstractmethod
    def analyzer_name(self) -> str:
        """Return the stable analyser identifier."""
