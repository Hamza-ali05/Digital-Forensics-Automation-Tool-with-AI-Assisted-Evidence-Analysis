"""Extract numeric forensic features from artefact ``raw_data`` for ML training."""

from __future__ import annotations

import ipaddress
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact

_SUSPICIOUS_PROCESS_NAMES = frozenset(
    {
        "mimikatz",
        "psexec",
        "procdump",
        "lazagne",
        "bloodhound",
        "rubeus",
        "sharphound",
        "cobaltstrike",
        "beacon",
        "meterpreter",
        "pwdump",
        "wce",
        "netcat",
        "ncat",
        "nc.exe",
    }
)

_SYSTEM_PARENTS = frozenset(
    {
        "system",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "services.exe",
        "lsass.exe",
        "winlogon.exe",
        "svchost.exe",
    }
)

_TEMP_MARKERS = (
    "\\temp\\",
    "/temp/",
    "\\tmp\\",
    "/tmp/",
    "%temp%",
    "appdata\\local\\temp",
    "appdata/local/temp",
)

_SYSTEM_DIR_MARKERS = (
    "windows\\system32",
    "windows/system32",
    "windows\\syswow64",
    "windows/syswow64",
    "program files",
)

_HIGH_RISK_EXTENSIONS = frozenset({".ps1", ".vbs", ".bat", ".cmd", ".hta", ".scr", ".js", ".jar", ".msi"})
_MEDIUM_RISK_EXTENSIONS = frozenset({".exe", ".dll", ".com", ".pif", ".sys"})
_MACRO_EXTENSIONS = frozenset({".docm", ".xlsm", ".pptm"})
_LOW_RISK_EXTENSIONS = frozenset({".txt", ".log", ".csv", ".json", ".xml"})

_SUSPICIOUS_PORTS = frozenset({4444, 4443, 5555, 6666, 6667, 1337, 31337, 8080, 8443, 12345})

_AUTORUN_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"CurrentVersion\\Run",
        r"Winlogon\\(Userinit|Shell)",
        r"Image File Execution Options",
        r"CurrentVersion\\Explorer\\StartupApproved",
    )
)

_HIVE_CATEGORY = {
    "system": 1.0,
    "software": 2.0,
    "sam": 3.0,
    "security": 4.0,
    "ntuser": 5.0,
    "usrclass": 5.0,
}

_PROTOCOL_CATEGORY = {
    "tcp": 1.0,
    "tcpv4": 1.0,
    "tcpv6": 1.0,
    "udp": 2.0,
    "udpv4": 2.0,
    "udpv6": 2.0,
}

_STATE_CATEGORY = {
    "listen": 1.0,
    "listening": 1.0,
    "established": 2.0,
    "syn_sent": 3.0,
    "syn_recv": 3.0,
    "time_wait": 4.0,
    "close_wait": 4.0,
    "closed": 0.0,
}

CATEGORY_FEATURE_NAMES: tuple[str, ...] = (
    "category_process",
    "category_file",
    "category_network",
    "category_registry",
    "category_other",
)

PROCESS_FEATURE_NAMES: tuple[str, ...] = (
    "name_length",
    "has_suspicious_name",
    "parent_is_system",
    "thread_count",
    "handle_count",
    "is_from_temp_dir",
    "has_network_connection",
)

FILE_FEATURE_NAMES: tuple[str, ...] = (
    "extension_risk_score",
    "is_deleted",
    "is_hidden",
    "size_category",
    "age_days",
    "in_system_directory",
)

NETWORK_FEATURE_NAMES: tuple[str, ...] = (
    "is_external",
    "port_is_suspicious",
    "protocol_category",
    "connection_state_category",
)

REGISTRY_FEATURE_NAMES: tuple[str, ...] = (
    "is_autorun",
    "hive_category",
    "depth",
    "value_length",
)

ALL_FEATURE_NAMES: tuple[str, ...] = (
    CATEGORY_FEATURE_NAMES
    + PROCESS_FEATURE_NAMES
    + FILE_FEATURE_NAMES
    + NETWORK_FEATURE_NAMES
    + REGISTRY_FEATURE_NAMES
)


def select_feature_matrix(features: Any, feature_names: Sequence[str]) -> Any:
    """Return a 2D numeric matrix containing only ``feature_names``.

    Accepts a list of feature dicts, or a 2D array whose columns follow
    ``feature_names`` or ``ALL_FEATURE_NAMES``.
    """
    names = list(feature_names)
    if isinstance(features, list) and features and isinstance(features[0], dict):
        rows = [[float(row.get(name, 0.0) or 0.0) for name in names] for row in features]
        return _as_2d(rows)
    array = _as_2d(features)
    if array.shape[1] == len(names):
        return array
    if array.shape[1] == len(ALL_FEATURE_NAMES):
        indexes = [ALL_FEATURE_NAMES.index(name) for name in names]
        return array[:, indexes]
    return array


def _as_2d(features: Any) -> Any:
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - optional dependency
        rows = list(features)
        if rows and not isinstance(rows[0], (list, tuple)):
            return [rows]
        return rows
    array = np.asarray(features, dtype=float)
    if array.ndim == 1:
        return array.reshape(1, -1)
    return array


class ForensicFeatureExtractor:
    """Convert forensic artefacts into numeric feature dictionaries for ML."""

    def extract_process_features(self, artefact: Artefact) -> dict[str, Any]:
        """Extract process-level features from a running-process artefact."""
        raw = _raw(artefact)
        name = str(raw.get("name") or raw.get("process_name") or "")
        parent = str(raw.get("parent_name") or "")
        path = str(
            raw.get("path")
            or raw.get("image_path")
            or raw.get("command_line")
            or artefact.source_path
            or ""
        )
        return {
            "name_length": float(len(name)),
            "has_suspicious_name": _has_suspicious_process_name(name),
            "parent_is_system": _parent_is_system(parent, raw.get("ppid")),
            "thread_count": _as_float(raw.get("threads") or raw.get("thread_count")),
            "handle_count": _as_float(raw.get("handles") or raw.get("handle_count")),
            "is_from_temp_dir": _is_temp_path(path),
            "has_network_connection": _process_has_network(raw, path),
        }

    def extract_file_features(self, artefact: Artefact) -> dict[str, Any]:
        """Extract filesystem metadata features from a file artefact."""
        raw = _raw(artefact)
        filename = str(raw.get("filename") or "")
        path = str(raw.get("path") or artefact.source_path or filename)
        extension = Path(filename or path).suffix.lower()
        size = _as_float(raw.get("size") or raw.get("file_size") or raw.get("size_bytes"))
        hidden_flag = raw.get("is_hidden")
        is_hidden = bool(hidden_flag) if hidden_flag is not None else _filename_is_hidden(filename)
        return {
            "extension_risk_score": _extension_risk_score(extension),
            "is_deleted": bool(raw.get("is_deleted")),
            "is_hidden": is_hidden,
            "size_category": _size_category(size),
            "age_days": _age_days(raw, artefact.parsed_at),
            "in_system_directory": _in_system_directory(path),
        }

    def extract_network_features(self, artefact: Artefact) -> dict[str, Any]:
        """Extract network-connection features from a network artefact."""
        raw = _raw(artefact)
        remote = str(raw.get("remote_address") or raw.get("destination_ip") or "")
        port = _as_int(raw.get("remote_port") or raw.get("dest_port") or raw.get("port"))
        protocol = str(raw.get("protocol") or "").lower()
        state = str(raw.get("state") or raw.get("connection_state") or "").lower()
        external_flag = raw.get("is_external")
        is_external = bool(external_flag) if external_flag is not None else _is_public_ip(remote)
        return {
            "is_external": is_external,
            "port_is_suspicious": port in _SUSPICIOUS_PORTS,
            "protocol_category": _PROTOCOL_CATEGORY.get(protocol, 0.0),
            "connection_state_category": _STATE_CATEGORY.get(state, 0.0),
        }

    def extract_registry_features(self, artefact: Artefact) -> dict[str, Any]:
        """Extract registry-key features from a registry artefact."""
        raw = _raw(artefact)
        key_path = str(raw.get("key_path") or artefact.source_path or "")
        hive = str(raw.get("hive_name") or _hive_from_path(key_path)).lower()
        value = str(raw.get("value_data") or raw.get("value") or "")
        return {
            "is_autorun": _is_autorun(key_path),
            "hive_category": _hive_category(hive),
            "depth": float(key_path.count("\\") + key_path.count("/")),
            "value_length": float(len(value)),
        }

    def extract_all(self, artefact: Artefact) -> dict[str, Any]:
        """Route to the category extractor and return a unified feature vector."""
        features = {name: 0.0 for name in ALL_FEATURE_NAMES}
        category = artefact.category
        features.update(_category_flags(category))

        if category is ArtefactCategory.RUNNING_PROCESS or category is ArtefactCategory.INJECTED_CODE:
            features.update(_numeric(self.extract_process_features(artefact)))
        elif category is ArtefactCategory.FILESYSTEM_METADATA:
            features.update(_numeric(self.extract_file_features(artefact)))
        elif category is ArtefactCategory.NETWORK_CONNECTION:
            features.update(_numeric(self.extract_network_features(artefact)))
        elif category is ArtefactCategory.REGISTRY_KEY:
            features.update(_numeric(self.extract_registry_features(artefact)))
        return features


def _raw(artefact: Artefact) -> dict[str, Any]:
    return artefact.raw_data if isinstance(artefact.raw_data, dict) else {}


def _category_flags(category: ArtefactCategory) -> dict[str, float]:
    flags = {name: 0.0 for name in CATEGORY_FEATURE_NAMES}
    mapping = {
        ArtefactCategory.RUNNING_PROCESS: "category_process",
        ArtefactCategory.INJECTED_CODE: "category_process",
        ArtefactCategory.FILESYSTEM_METADATA: "category_file",
        ArtefactCategory.NETWORK_CONNECTION: "category_network",
        ArtefactCategory.REGISTRY_KEY: "category_registry",
    }
    flags[mapping.get(category, "category_other")] = 1.0
    return flags


def _numeric(features: dict[str, Any]) -> dict[str, float]:
    converted: dict[str, float] = {}
    for key, value in features.items():
        if isinstance(value, bool):
            converted[key] = 1.0 if value else 0.0
        else:
            converted[key] = _as_float(value)
    return converted


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _has_suspicious_process_name(name: str) -> bool:
    lowered = name.lower().strip()
    stem = Path(lowered).stem
    if lowered in _SUSPICIOUS_PROCESS_NAMES or stem in _SUSPICIOUS_PROCESS_NAMES:
        return True
    return any(token in lowered for token in _SUSPICIOUS_PROCESS_NAMES)


def _parent_is_system(parent_name: str, ppid: Any) -> bool:
    parent = parent_name.lower().strip()
    if parent in _SYSTEM_PARENTS:
        return True
    return _as_int(ppid) in {0, 4}


def _is_temp_path(path: str) -> bool:
    lowered = path.lower().replace("/", "\\")
    return any(marker.replace("/", "\\") in lowered for marker in _TEMP_MARKERS)


def _in_system_directory(path: str) -> bool:
    lowered = path.lower().replace("/", "\\")
    return any(marker.replace("/", "\\") in lowered for marker in _SYSTEM_DIR_MARKERS)


def _process_has_network(raw: dict[str, Any], path: str) -> bool:
    if raw.get("has_network_connection") is True:
        return True
    connections = raw.get("connections") or raw.get("network_connections")
    if isinstance(connections, list) and connections:
        return True
    lowered = path.lower()
    return "http://" in lowered or "https://" in lowered or bool(raw.get("remote_address"))


def _filename_is_hidden(filename: str) -> bool:
    name = Path(filename).name
    return name.startswith(".") or name.startswith("$")


def _extension_risk_score(extension: str) -> float:
    if extension in _HIGH_RISK_EXTENSIONS:
        return 0.9
    if extension in _MEDIUM_RISK_EXTENSIONS:
        return 0.6
    if extension in _MACRO_EXTENSIONS:
        return 0.5
    if extension in _LOW_RISK_EXTENSIONS:
        return 0.1
    if not extension:
        return 0.3
    return 0.2


def _size_category(size: float) -> float:
    if size <= 1024:
        return 0.0
    if size <= 100 * 1024:
        return 1.0
    if size <= 1024 * 1024:
        return 2.0
    if size <= 10 * 1024 * 1024:
        return 3.0
    return 4.0


def _age_days(raw: dict[str, Any], parsed_at: datetime) -> float:
    timestamp = raw.get("modified_time") or raw.get("created_time") or raw.get("create_time")
    if not timestamp:
        return 0.0
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return 0.0
    reference = parsed_at if parsed_at.tzinfo else parsed_at.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age = (reference - parsed).total_seconds() / 86400.0
    return max(0.0, age)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_public_ip(address: str) -> bool:
    host = address.split("%", maxsplit=1)[0].strip()
    if not host or host in {"*", "0.0.0.0", "::"}:
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return False


def _is_autorun(key_path: str) -> bool:
    return any(pattern.search(key_path) for pattern in _AUTORUN_PATTERNS)


def _hive_from_path(key_path: str) -> str:
    prefix = key_path.split("\\", maxsplit=1)[0].split("/", maxsplit=1)[0]
    mapping = {
        "HKLM": "SYSTEM",
        "HKEY_LOCAL_MACHINE": "SYSTEM",
        "HKCU": "NTUSER",
        "HKEY_CURRENT_USER": "NTUSER",
        "HKU": "NTUSER",
    }
    return mapping.get(prefix, prefix)


def _hive_category(hive: str) -> float:
    lowered = hive.lower()
    for key, value in _HIVE_CATEGORY.items():
        if key in lowered:
            return value
    return 0.0
