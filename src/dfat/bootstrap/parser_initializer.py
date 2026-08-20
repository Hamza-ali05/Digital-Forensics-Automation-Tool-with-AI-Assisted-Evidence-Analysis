"""Forensic parser library availability checks for bootstrap."""

from __future__ import annotations

import importlib
import logging
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any, ClassVar, Optional

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.pipeline.parser_registry import ParserRegistry

logger = logging.getLogger(__name__)

_PACKAGE_NAME_MAP: dict[str, str] = {
    "Registry": "python-registry",
    "Evtx": "python-evtx",
    "pytsk3": "pytsk3",
    "volatility3": "volatility3",
}


class ParserInitializer:
    """Probe forensic parser dependencies without aborting startup."""

    LIBRARY_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        "FileSystemParser": ("pytsk3", "pip install pytsk3"),
        "RegistryParser": ("Registry", "pip install python-registry"),
        "BrowserHistoryParser": ("sqlite3", "builtin"),
        "EventLogParser": ("Evtx", "pip install python-evtx"),
        "ProcessListParser": ("volatility3", "pip install volatility3"),
        "NetworkArtefactParser": ("volatility3", "pip install volatility3"),
        "CodeInjectionParser": ("volatility3", "pip install volatility3"),
        "MemoryRegistryParser": ("volatility3", "pip install volatility3"),
    }

    def __init__(self, parser_registry: ParserRegistry) -> None:
        """Initialise the parser bootstrap helper.

        Args:
            parser_registry: Registered artefact parsers to probe.
        """
        self._registry = parser_registry

    async def initialize(self) -> PhaseResult:
        """Check each registered parser's required library independently.

        Returns:
            ``PhaseResult`` with ``COMPLETED`` or ``DEGRADED`` (never critical).
        """
        started = time.perf_counter()
        availability: dict[str, dict[str, Any]] = {}
        degraded: list[str] = []

        parsers = self._registry.get_all_parsers()
        if not parsers:
            duration_ms = (time.perf_counter() - started) * 1000.0
            return PhaseResult(
                phase=InitPhase.FORENSIC_PARSERS,
                status=InitStatus.DEGRADED,
                duration_ms=duration_ms,
                message="No forensic parsers registered",
                details={"parsers": availability},
                is_critical=False,
                degraded_capabilities=["forensic_parsers"],
            )

        for parser in parsers:
            name = parser.parser_name
            mapping = self.LIBRARY_MAP.get(name)
            if mapping is None:
                available = self._registry.is_parser_available(parser)
                availability[name] = {
                    "available": available,
                    "library": "unknown",
                    "version": None,
                    "install": "No bootstrap library map entry; see parser docs.",
                }
                if not available:
                    degraded.append(name)
                    logger.warning(
                        "Parser %s unavailable (no LIBRARY_MAP entry).",
                        name,
                    )
                continue

            library_name, install_hint = mapping
            available, version_str = self._check_library(library_name)
            availability[name] = {
                "available": available,
                "library": library_name,
                "version": version_str,
                "install": install_hint,
            }
            if not available:
                degraded.append(name)
                logger.warning(
                    "Parser %s unavailable — install with: %s",
                    name,
                    install_hint,
                )

        duration_ms = (time.perf_counter() - started) * 1000.0
        available_count = sum(1 for item in availability.values() if item["available"])
        all_unavailable = available_count == 0

        status = InitStatus.DEGRADED if all_unavailable else InitStatus.COMPLETED
        if degraded and not all_unavailable:
            status = InitStatus.COMPLETED

        message = (
            "All forensic parsers unavailable — parsing degraded"
            if all_unavailable
            else (
                f"Forensic parsers ready ({available_count}/{len(availability)} available)"
                if not degraded
                else (
                    f"Forensic parsers partially available "
                    f"({available_count}/{len(availability)})"
                )
            )
        )

        return PhaseResult(
            phase=InitPhase.FORENSIC_PARSERS,
            status=status,
            duration_ms=duration_ms,
            message=message,
            details={"parsers": availability, "unavailable": degraded},
            is_critical=False,
            degraded_capabilities=degraded,
        )

    def _check_library(self, library_name: str) -> tuple[bool, Optional[str]]:
        """Try importing ``library_name`` and return availability + version.

        Args:
            library_name: Importable module name or ``builtin`` sentinel.

        Returns:
            ``(available, version_string)`` where version may be ``None``.
        """
        if library_name == "builtin":
            return True, "builtin"
        try:
            module = importlib.import_module(library_name)
        except ImportError:
            return False, None

        version_str: Optional[str] = None
        if library_name == "sqlite3":
            version_str = str(getattr(module, "sqlite_version", "builtin"))
        else:
            package = _PACKAGE_NAME_MAP.get(library_name, library_name)
            try:
                version_str = version(package)
            except PackageNotFoundError:
                version_str = str(getattr(module, "__version__", "unknown"))
        return True, version_str
