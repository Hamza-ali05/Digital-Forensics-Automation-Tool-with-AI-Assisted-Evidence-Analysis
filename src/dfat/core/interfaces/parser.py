"""Abstract artefact parser port for forensic engine implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evidence import EvidenceImage


class IArtefactParser(ABC):
    """Port for extracting artefacts from forensic evidence."""

    @abstractmethod
    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Parse evidence and return a normalised artefact set.

        Args:
            evidence: Evidence image or dump metadata to parse.

        Returns:
            Normalised artefact set extracted from the evidence.
        """

    @abstractmethod
    def supported_categories(self) -> list[ArtefactCategory]:
        """Return artefact categories this parser can produce.

        Returns:
            List of supported artefact categories.
        """

    @abstractmethod
    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return evidence types this parser can process.

        Returns:
            List of supported evidence types.
        """

    @property
    @abstractmethod
    def parser_name(self) -> str:
        """Return the stable parser identifier."""
