"""Registry of artefact parsers keyed by evidence type and name."""

from __future__ import annotations

import importlib
from typing import Optional

from dfat.core.enums import EvidenceType
from dfat.core.interfaces.parser import IArtefactParser

# Preferred import probes when a parser does not expose ``is_available()``.
_PARSER_LIBRARY_PROBES: dict[str, tuple[str, ...]] = {
    "FileSystemParser": ("pytsk3",),
    "BrowserHistoryParser": ("pytsk3",),
    "RegistryParser": ("pytsk3", "Registry"),
    "EventLogParser": ("pytsk3", "Evtx"),
    "ProcessListParser": ("volatility3",),
    "NetworkArtefactParser": ("volatility3",),
    "CodeInjectionParser": ("volatility3",),
    "MemoryRegistryParser": ("volatility3",),
}

_EVIDENCE_TYPE_DEFAULT_LIBS: dict[EvidenceType, tuple[str, ...]] = {
    EvidenceType.DISK_IMAGE: ("pytsk3",),
    EvidenceType.MEMORY_DUMP: ("volatility3",),
}


class ParserRegistry:
    """Register and resolve ``IArtefactParser`` implementations."""

    def __init__(self) -> None:
        """Initialise an empty parser registry."""
        self._parsers: dict[str, IArtefactParser] = {}

    def register(self, parser: IArtefactParser) -> None:
        """Register a parser, replacing any prior entry with the same name.

        Args:
            parser: Artefact parser implementation.
        """
        self._parsers[parser.parser_name] = parser

    def get_parsers_for_type(
        self,
        evidence_type: EvidenceType,
    ) -> list[IArtefactParser]:
        """Return parsers that declare support for ``evidence_type``.

        Args:
            evidence_type: Disk image or memory dump classification.

        Returns:
            Matching parsers in registration order.
        """
        return [
            parser
            for parser in self._parsers.values()
            if evidence_type in parser.supported_evidence_types()
        ]

    def get_all_parsers(self) -> list[IArtefactParser]:
        """Return all registered parsers."""
        return list(self._parsers.values())

    def get_parser_by_name(self, name: str) -> Optional[IArtefactParser]:
        """Return a parser by stable name, or ``None`` if unknown."""
        return self._parsers.get(name)

    def check_availability(self) -> dict[str, bool]:
        """Probe whether each parser's required libraries are importable.

        Prefers ``parser.is_available()`` when implemented; otherwise performs
        a test import of known dependency modules.

        Returns:
            Mapping of ``parser_name`` → availability flag.
        """
        return {
            name: self.is_parser_available(parser)
            for name, parser in self._parsers.items()
        }

    def is_parser_available(self, parser: IArtefactParser) -> bool:
        """Return whether ``parser`` can run in this environment."""
        checker = getattr(parser, "is_available", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:  # noqa: BLE001 — treat probe failures as unavailable
                return False
        return self._libraries_importable(parser)

    def _libraries_importable(self, parser: IArtefactParser) -> bool:
        """Attempt test-imports for libraries required by ``parser``."""
        modules = _PARSER_LIBRARY_PROBES.get(parser.parser_name)
        if modules is None:
            modules = ()
            for evidence_type in parser.supported_evidence_types():
                modules = modules + _EVIDENCE_TYPE_DEFAULT_LIBS.get(evidence_type, ())
            if not modules:
                return True
        return all(self._can_import(module) for module in modules)

    @staticmethod
    def _can_import(module_name: str) -> bool:
        """Return whether ``module_name`` can be imported."""
        try:
            importlib.import_module(module_name)
        except ImportError:
            return False
        return True
