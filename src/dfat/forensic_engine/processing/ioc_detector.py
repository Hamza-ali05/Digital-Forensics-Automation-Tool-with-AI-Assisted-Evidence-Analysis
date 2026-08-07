"""IOC identification — pattern-based threat indicator classification."""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.parsers.utils import sanitise_path

logger = logging.getLogger(__name__)

SUSPICIOUS_PROCESSES: list[str] = [
    "mimikatz",
    "psexec",
    "procdump",
    "lazagne",
    "bloodhound",
    "rubeus",
    "sharphound",
    "cobalt",
    "beacon",
]

SUSPICIOUS_REGISTRY_PATHS: list[str] = [
    "\\Run\\",
    "\\RunOnce\\",
    "\\Services\\",
    "\\Winlogon\\Shell",
    "\\Image File Execution Options\\",
]

SUSPICIOUS_EXTENSIONS: list[str] = [
    ".ps1",
    ".vbs",
    ".bat",
    ".cmd",
    ".hta",
    ".scr",
]

EXTERNAL_PORT_INDICATORS: list[int] = [
    4444,
    5555,
    8080,
    1337,
    31337,
    6666,
    6667,
]


class IOCMatch(BaseModel):
    """A single indicator-of-compromise match against an artefact.

    Attributes:
        artefact_id: Source artefact identifier.
        ioc_type: Broad IOC family (process, registry, network, …).
        indicator: Concrete matched value (name, path, port, …).
        confidence: ``high`` / ``medium`` / ``low``.
        description: Human-readable explanation.
        matched_rule: Stable rule identifier that fired.
    """

    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)

    artefact_id: str
    ioc_type: str
    indicator: str
    confidence: str = Field(pattern="^(high|medium|low)$")
    description: str
    matched_rule: str


class IOCDetector:
    """Scan artefacts for known threat indicators via pattern matching."""

    def detect(self, artefact_set: ArtefactSet) -> list[IOCMatch]:
        """Scan all artefacts against IOC pattern libraries.

        Rules covered:
            1. Suspicious process names
            2. Suspicious registry paths
            3. Suspicious file extensions
            4. Known malicious/external ports
            5. External network connections
            6. Injected-code findings (all)
            7. Deleted files with suspicious extensions

        Args:
            artefact_set: Artefact collection to scan.

        Returns:
            List of ``IOCMatch`` results (may be empty).
        """
        matches: list[IOCMatch] = []
        for artefact in artefact_set.artefacts:
            matches.extend(self._scan_artefact(artefact))

        logger.info(
            "IOC scan for evidence %s: %d match(es) across %d artefacts",
            artefact_set.evidence_id,
            len(matches),
            len(artefact_set.artefacts),
        )
        return matches

    def _scan_artefact(self, artefact: Artefact) -> list[IOCMatch]:
        """Apply category-specific IOC rules to one artefact."""
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        category = artefact.category

        if category is ArtefactCategory.RUNNING_PROCESS:
            return self._scan_process(artefact, raw)
        if category is ArtefactCategory.REGISTRY_KEY:
            return self._scan_registry(artefact, raw)
        if category is ArtefactCategory.FILESYSTEM_METADATA:
            return self._scan_filesystem(artefact, raw)
        if category is ArtefactCategory.NETWORK_CONNECTION:
            return self._scan_network(artefact, raw)
        if category is ArtefactCategory.INJECTED_CODE:
            return self._scan_injection(artefact, raw)
        return []

    def _scan_process(self, artefact: Artefact, raw: dict[str, Any]) -> list[IOCMatch]:
        """Match process names against ``SUSPICIOUS_PROCESSES``."""
        matches: list[IOCMatch] = []
        name = str(raw.get("name") or raw.get("process_name") or "")
        cmdline = str(raw.get("command_line") or "")
        haystacks = [name, cmdline]
        for process in SUSPICIOUS_PROCESSES:
            needle = process.lower()
            if any(needle in text.lower() for text in haystacks if text):
                matches.append(
                    IOCMatch(
                        artefact_id=artefact.artefact_id,
                        ioc_type="suspicious_process",
                        indicator=process,
                        confidence="high",
                        description=(
                            f"Process artefact references known suspicious tool "
                            f"'{process}'"
                        ),
                        matched_rule="SUSPICIOUS_PROCESSES",
                    )
                )
        return matches

    def _scan_registry(self, artefact: Artefact, raw: dict[str, Any]) -> list[IOCMatch]:
        """Match registry key paths against ``SUSPICIOUS_REGISTRY_PATHS``."""
        matches: list[IOCMatch] = []
        key_path = str(raw.get("key_path") or "")
        normalised = key_path.replace("/", "\\")
        for pattern in SUSPICIOUS_REGISTRY_PATHS:
            if pattern.lower() in normalised.lower():
                matches.append(
                    IOCMatch(
                        artefact_id=artefact.artefact_id,
                        ioc_type="suspicious_registry",
                        indicator=pattern,
                        confidence="medium",
                        description=(
                            f"Registry key path matches persistence/abuse pattern "
                            f"'{pattern}'"
                        ),
                        matched_rule="SUSPICIOUS_REGISTRY_PATHS",
                    )
                )
        # Also flag suspicious extensions in registry values.
        value_data = str(raw.get("value_data") or "")
        ext = self._suspicious_extension(value_data)
        if ext is not None:
            matches.append(
                IOCMatch(
                    artefact_id=artefact.artefact_id,
                    ioc_type="suspicious_extension",
                    indicator=ext,
                    confidence="medium",
                    description=(
                        f"Registry value references a suspicious extension '{ext}'"
                    ),
                    matched_rule="SUSPICIOUS_EXTENSIONS",
                )
            )
        return matches

    def _scan_filesystem(
        self,
        artefact: Artefact,
        raw: dict[str, Any],
    ) -> list[IOCMatch]:
        """Match file paths/extensions; elevate confidence for deleted files."""
        matches: list[IOCMatch] = []
        path = str(raw.get("path") or raw.get("filename") or "")
        ext = self._suspicious_extension(path)
        if ext is None:
            return matches

        is_deleted = raw.get("is_deleted") is True
        if is_deleted:
            matches.append(
                IOCMatch(
                    artefact_id=artefact.artefact_id,
                    ioc_type="deleted_suspicious_file",
                    indicator=ext,
                    confidence="high",
                    description=(
                        f"Deleted file with suspicious extension '{ext}': {path}"
                    ),
                    matched_rule="SUSPICIOUS_EXTENSIONS+DELETED",
                )
            )
        else:
            matches.append(
                IOCMatch(
                    artefact_id=artefact.artefact_id,
                    ioc_type="suspicious_extension",
                    indicator=ext,
                    confidence="low",
                    description=f"File with suspicious extension '{ext}': {path}",
                    matched_rule="SUSPICIOUS_EXTENSIONS",
                )
            )
        return matches

    def _scan_network(self, artefact: Artefact, raw: dict[str, Any]) -> list[IOCMatch]:
        """Match ports and external remote addresses."""
        matches: list[IOCMatch] = []
        for port_key in ("remote_port", "local_port"):
            port = self._as_int(raw.get(port_key))
            if port is not None and port in EXTERNAL_PORT_INDICATORS:
                matches.append(
                    IOCMatch(
                        artefact_id=artefact.artefact_id,
                        ioc_type="suspicious_port",
                        indicator=str(port),
                        confidence="high",
                        description=(
                            f"Network connection uses known suspicious port "
                            f"{port} ({port_key})"
                        ),
                        matched_rule="EXTERNAL_PORT_INDICATORS",
                    )
                )

        if raw.get("is_external") is True:
            remote = str(raw.get("remote_address") or "")
            matches.append(
                IOCMatch(
                    artefact_id=artefact.artefact_id,
                    ioc_type="external_connection",
                    indicator=remote or "unknown",
                    confidence="medium",
                    description=(
                        f"Network connection to external address '{remote}'"
                    ),
                    matched_rule="EXTERNAL_IP",
                )
            )
        return matches

    def _scan_injection(
        self,
        artefact: Artefact,
        raw: dict[str, Any],
    ) -> list[IOCMatch]:
        """Treat all injected-code findings as IOCs."""
        indicators = raw.get("suspicious_indicators") or []
        if isinstance(indicators, list) and indicators:
            indicator = ", ".join(str(item) for item in indicators)
            confidence = "high"
        else:
            indicator = str(raw.get("vad_start") or "injected_region")
            confidence = "medium"
        process = raw.get("process_name") or raw.get("pid") or "unknown"
        return [
            IOCMatch(
                artefact_id=artefact.artefact_id,
                ioc_type="injected_code",
                indicator=indicator,
                confidence=confidence,
                description=f"Injected code finding in process '{process}'",
                matched_rule="INJECTED_CODE",
            )
        ]

    @staticmethod
    def _suspicious_extension(path: str) -> Optional[str]:
        """Return the matching suspicious extension, if any."""
        if not path:
            return None
        normalised = sanitise_path(path.strip().strip('"')).lower()
        # Strip arguments after executable path.
        token = normalised.split()[0] if normalised else ""
        for ext in SUSPICIOUS_EXTENSIONS:
            if token.endswith(ext.lower()):
                return ext.lower()
        return None

    @staticmethod
    def _as_int(value: Any) -> Optional[int]:
        """Best-effort integer coercion."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
