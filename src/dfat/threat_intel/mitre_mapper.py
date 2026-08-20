"""MITRE ATT&CK technique mapping for ranked forensic artefacts."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact

_SUSPICIOUS_PORTS = frozenset({4444, 4443, 5555, 6666, 6667, 1337, 31337, 8080, 8443, 12345})
_AUTORUN_KEY = re.compile(r"CurrentVersion\\Run", re.IGNORECASE)
_SERVICE_EVENT_IDS = frozenset({"7045", "4697"})


class MITREMapping(BaseModel):
    """Mapping between a forensic artefact and a MITRE ATT&CK technique."""

    model_config = ConfigDict(frozen=False)

    artefact_id: str
    technique_id: str
    technique_name: str
    tactic: str
    confidence: str
    evidence: str


_TECHNIQUE_INFO: dict[str, dict[str, str]] = {
    "T1547.001": {
        "technique_name": "Boot or Logon Autostart Execution: Registry Run Keys",
        "tactic": "Persistence",
    },
    "T1055": {
        "technique_name": "Process Injection",
        "tactic": "Defense Evasion",
    },
    "T1071": {
        "technique_name": "Application Layer Protocol",
        "tactic": "Command and Control",
    },
    "T1543.003": {
        "technique_name": "Create or Modify System Process: Windows Service",
        "tactic": "Persistence",
    },
    "T1059.001": {
        "technique_name": "Command and Scripting Interpreter: PowerShell",
        "tactic": "Execution",
    },
    "T1078": {
        "technique_name": "Valid Accounts",
        "tactic": "Defense Evasion",
    },
    "T1027": {
        "technique_name": "Obfuscated Files or Information",
        "tactic": "Defense Evasion",
    },
    "T1003": {
        "technique_name": "OS Credential Dumping",
        "tactic": "Credential Access",
    },
    "T1105": {
        "technique_name": "Ingress Tool Transfer",
        "tactic": "Command and Control",
    },
    "T1566": {
        "technique_name": "Phishing",
        "tactic": "Initial Access",
    },
}


class MITREMapper:
    """Map ranked forensic artefacts to MITRE ATT&CK techniques."""

    TECHNIQUE_DB: dict[str, dict[str, str]] = _TECHNIQUE_INFO

    def map_artefact(self, artefact: RankedArtefact) -> list[MITREMapping]:
        """Return ATT&CK mappings for a single ranked artefact."""
        mappings: list[MITREMapping] = []
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        metadata = artefact.metadata if isinstance(artefact.metadata, dict) else {}

        mappings.extend(self._map_registry_autorun(artefact, raw))
        mappings.extend(self._map_process_injection(artefact, raw))
        mappings.extend(self._map_network_c2(artefact, raw))
        mappings.extend(self._map_service_creation(artefact, raw))
        mappings.extend(self._map_powershell(artefact, raw))
        mappings.extend(self._map_credential_dumping(artefact, raw))
        mappings.extend(self._map_obfuscated_file(artefact, raw))
        mappings.extend(self._map_from_metadata(artefact, metadata))

        if not mappings and artefact.suspicion_level in {
            SuspicionLevel.HIGH,
            SuspicionLevel.CRITICAL,
        }:
            mappings.append(
                MITREMapping(
                    artefact_id=artefact.artefact_id,
                    technique_id="T1078",
                    technique_name=self.TECHNIQUE_DB["T1078"]["technique_name"],
                    tactic=self.TECHNIQUE_DB["T1078"]["tactic"],
                    confidence="low",
                    evidence=f"High suspicion {artefact.category.value} artefact without specific technique match",
                )
            )
        return _dedupe_mappings(mappings)

    def map_artefact_set(self, ranked: list[RankedArtefact]) -> list[MITREMapping]:
        """Return ATT&CK mappings for every ranked artefact."""
        results: list[MITREMapping] = []
        for artefact in ranked:
            results.extend(self.map_artefact(artefact))
        return _dedupe_mappings(results)

    def get_technique_info(self, technique_id: str) -> dict[str, str]:
        """Return metadata for a known technique identifier."""
        info = self.TECHNIQUE_DB.get(technique_id)
        if info is None:
            return {
                "technique_id": technique_id,
                "technique_name": "Unknown technique",
                "tactic": "Unknown",
            }
        return {"technique_id": technique_id, **info}

    def get_tactic_coverage(self, mappings: list[MITREMapping]) -> dict[str, list[str]]:
        """Summarise which ATT&CK tactics are represented in ``mappings``."""
        coverage: dict[str, set[str]] = {}
        for mapping in mappings:
            coverage.setdefault(mapping.tactic, set()).add(mapping.technique_id)
        return {
            tactic: sorted(technique_ids)
            for tactic, technique_ids in sorted(coverage.items())
        }

    def _map_registry_autorun(
        self,
        artefact: RankedArtefact,
        raw: dict[str, Any],
    ) -> list[MITREMapping]:
        if artefact.category is not ArtefactCategory.REGISTRY_KEY:
            return []
        key_path = str(raw.get("key_path") or raw.get("KeyPath") or "")
        if not _AUTORUN_KEY.search(key_path):
            return []
        return [
            _mapping(
                artefact.artefact_id,
                "T1547.001",
                "high",
                f"Registry autorun key: {key_path}",
            )
        ]

    def _map_process_injection(
        self,
        artefact: RankedArtefact,
        raw: dict[str, Any],
    ) -> list[MITREMapping]:
        if artefact.category not in {
            ArtefactCategory.INJECTED_CODE,
            ArtefactCategory.RUNNING_PROCESS,
        }:
            return []
        indicators = raw.get("suspicious_indicators") or raw.get("indicators") or []
        protection = str(raw.get("protection") or raw.get("Protect") or "")
        process_name = str(raw.get("process_name") or raw.get("name") or "")
        if artefact.category is ArtefactCategory.INJECTED_CODE:
            evidence = f"Injected code region in {process_name or 'unknown process'}"
            return [_mapping(artefact.artefact_id, "T1055", "high", evidence)]
        if protection.upper() == "RWX" or any(
            str(item).lower() in {"malfind", "injection", "hollow"} for item in indicators
        ):
            return [
                _mapping(
                    artefact.artefact_id,
                    "T1055",
                    "medium",
                    f"Process injection indicator for {process_name or 'unknown process'}",
                )
            ]
        return []

    def _map_network_c2(
        self,
        artefact: RankedArtefact,
        raw: dict[str, Any],
    ) -> list[MITREMapping]:
        if artefact.category is not ArtefactCategory.NETWORK_CONNECTION:
            return []
        port = _as_int(raw.get("remote_port") or raw.get("dport") or raw.get("port"))
        is_external = bool(raw.get("is_external"))
        if port in _SUSPICIOUS_PORTS or (is_external and port is not None):
            remote = raw.get("remote_address") or raw.get("destination") or "unknown"
            return [
                _mapping(
                    artefact.artefact_id,
                    "T1071",
                    "medium" if port in _SUSPICIOUS_PORTS else "low",
                    f"External connection to {remote}:{port}",
                )
            ]
        return []

    def _map_service_creation(
        self,
        artefact: RankedArtefact,
        raw: dict[str, Any],
    ) -> list[MITREMapping]:
        if artefact.category is not ArtefactCategory.EVENT_LOG:
            return []
        event_id = str(raw.get("EventID") or raw.get("event_id") or raw.get("event_code") or "")
        provider = str(raw.get("ProviderName") or raw.get("source") or "").lower()
        if event_id in _SERVICE_EVENT_IDS or "service control manager" in provider:
            service = raw.get("ServiceName") or raw.get("service_name") or raw.get("ImagePath")
            return [
                _mapping(
                    artefact.artefact_id,
                    "T1543.003",
                    "high" if event_id == "7045" else "medium",
                    f"Windows service creation event ({event_id}): {service or 'unknown service'}",
                )
            ]
        return []

    def _map_powershell(
        self,
        artefact: RankedArtefact,
        raw: dict[str, Any],
    ) -> list[MITREMapping]:
        candidates = [
            str(raw.get("name") or ""),
            str(raw.get("process_name") or ""),
            str(raw.get("CommandLine") or raw.get("command_line") or ""),
            str(raw.get("Image") or raw.get("image") or ""),
            str(raw.get("filename") or raw.get("path") or ""),
        ]
        text = " ".join(candidates).lower()
        if "powershell" in text or ".ps1" in text:
            return [
                _mapping(
                    artefact.artefact_id,
                    "T1059.001",
                    "medium",
                    "PowerShell interpreter or script execution detected",
                )
            ]
        return []

    def _map_credential_dumping(
        self,
        artefact: RankedArtefact,
        raw: dict[str, Any],
    ) -> list[MITREMapping]:
        text = " ".join(str(value) for value in raw.values()).lower()
        keywords = ("mimikatz", "lsass", "sekurlsa", "procdump", "credential dump")
        if any(keyword in text for keyword in keywords):
            return [
                _mapping(
                    artefact.artefact_id,
                    "T1003",
                    "high",
                    "Credential dumping tool or LSASS access indicator",
                )
            ]
        return []

    def _map_obfuscated_file(
        self,
        artefact: RankedArtefact,
        raw: dict[str, Any],
    ) -> list[MITREMapping]:
        if artefact.category is not ArtefactCategory.FILESYSTEM_METADATA:
            return []
        filename = str(raw.get("filename") or raw.get("path") or "")
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension in {"ps1", "vbs", "hta", "js", "bat", "cmd"} and raw.get("is_hidden"):
            return [
                _mapping(
                    artefact.artefact_id,
                    "T1027",
                    "medium",
                    f"Potentially obfuscated script file: {filename}",
                )
            ]
        return []

    def _map_from_metadata(
        self,
        artefact: RankedArtefact,
        metadata: dict[str, Any],
    ) -> list[MITREMapping]:
        techniques = metadata.get("mitre_techniques") or metadata.get("attack_techniques") or []
        if not isinstance(techniques, list):
            return []
        mappings: list[MITREMapping] = []
        for technique_id in techniques:
            text = str(technique_id).strip()
            if not text:
                continue
            normalized = text.upper().replace("ATTACK.", "")
            info = self.get_technique_info(normalized)
            mappings.append(
                MITREMapping(
                    artefact_id=artefact.artefact_id,
                    technique_id=normalized,
                    technique_name=info["technique_name"],
                    tactic=info["tactic"],
                    confidence="medium",
                    evidence="Technique supplied in artefact metadata",
                )
            )
        return mappings


def _mapping(
    artefact_id: str,
    technique_id: str,
    confidence: str,
    evidence: str,
) -> MITREMapping:
    info = _TECHNIQUE_INFO[technique_id]
    return MITREMapping(
        artefact_id=artefact_id,
        technique_id=technique_id,
        technique_name=info["technique_name"],
        tactic=info["tactic"],
        confidence=confidence,
        evidence=evidence,
    )


def _dedupe_mappings(mappings: list[MITREMapping]) -> list[MITREMapping]:
    seen: set[tuple[str, str]] = set()
    deduped: list[MITREMapping] = []
    for mapping in mappings:
        key = (mapping.artefact_id, mapping.technique_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(mapping)
    return deduped


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
