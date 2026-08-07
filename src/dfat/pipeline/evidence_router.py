"""Route loaded evidence to the correct set of available artefact parsers."""

from __future__ import annotations

from dfat.core.enums import EvidenceType
from dfat.core.interfaces.parser import IArtefactParser
from dfat.pipeline.parser_registry import ParserRegistry


class EvidenceRouter:
    """Select available parsers for a given evidence type."""

    def __init__(self, parser_registry: ParserRegistry) -> None:
        """Initialise the evidence router.

        Args:
            parser_registry: Registry of artefact parsers.
        """
        self._registry = parser_registry

    def route(self, evidence_type: EvidenceType) -> list[IArtefactParser]:
        """Return available parsers that support ``evidence_type``.

        Filters out parsers whose required libraries are not installed
        (via ``parser.is_available()`` or a registry test-import probe).

        Args:
            evidence_type: Disk image or memory dump classification.

        Returns:
            Available parsers for the evidence type.
        """
        candidates = self._registry.get_parsers_for_type(evidence_type)
        return [
            parser
            for parser in candidates
            if self._registry.is_parser_available(parser)
        ]

    def get_available_parsers(self) -> dict[str, list[str]]:
        """Return available parser names grouped by evidence family.

        Returns:
            Mapping ``{"disk": [...], "memory": [...]}`` of parser names.
        """
        disk = [
            parser.parser_name
            for parser in self.route(EvidenceType.DISK_IMAGE)
        ]
        memory = [
            parser.parser_name
            for parser in self.route(EvidenceType.MEMORY_DUMP)
        ]
        return {"disk": disk, "memory": memory}
