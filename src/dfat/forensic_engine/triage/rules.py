"""Rule-based triage definitions — extensible declarative suspicion rules."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import ArtefactCategory
from dfat.forensic_engine.processing.ioc_detector import (
    EXTERNAL_PORT_INDICATORS,
    SUSPICIOUS_PROCESSES,
)

ConditionOperator = Literal[
    "contains",
    "equals",
    "regex",
    "greater_than",
    "in_list",
]


class TriageRule(BaseModel):
    """Declarative triage rule applied to artefact ``raw_data`` fields.

    Attributes:
        rule_id: Stable unique rule identifier.
        name: Short human-readable name.
        description: Investigator-facing explanation.
        category: Artefact category this rule applies to.
        condition_field: ``raw_data`` field name to evaluate
            (dot-path supported for nested dicts, e.g. ``event_data.ProcessId``).
        condition_operator: Comparison operator.
        condition_value: Expected value / pattern / list for the operator.
        suspicion_boost: Score increment applied when the rule matches
            (typically ``0.0``–``1.0``).
        tags: Free-form labels for filtering and reporting.
    """

    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)

    rule_id: str
    name: str
    description: str
    category: ArtefactCategory
    condition_field: str
    condition_operator: ConditionOperator
    condition_value: Any
    suspicion_boost: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


DEFAULT_TRIAGE_RULES: list[TriageRule] = [
    # ── Filesystem ──────────────────────────────────────────────────────────
    TriageRule(
        rule_id="FS-001",
        name="Deleted executable",
        description="Deleted file with an executable extension.",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        condition_field="path",
        condition_operator="regex",
        condition_value=r"(?i)\.(exe|dll|sys|com|scr)$",
        suspicion_boost=0.35,
        tags=["filesystem", "deleted", "executable"],
    ),
    TriageRule(
        rule_id="FS-002",
        name="Deleted flag set",
        description="Filesystem entry marked as deleted.",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        condition_field="is_deleted",
        condition_operator="equals",
        condition_value=True,
        suspicion_boost=0.2,
        tags=["filesystem", "deleted"],
    ),
    TriageRule(
        rule_id="FS-003",
        name="Hidden file attribute",
        description="File or directory flagged as hidden.",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        condition_field="file_type",
        condition_operator="contains",
        condition_value="hidden",
        suspicion_boost=0.15,
        tags=["filesystem", "hidden"],
    ),
    TriageRule(
        rule_id="FS-004",
        name="File in temporary directory",
        description="Path under a common temporary directory.",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        condition_field="path",
        condition_operator="regex",
        condition_value=r"(?i)(/|\\\\)(windows[/\\]temp|users[/\\][^/\\]+[/\\]appdata[/\\]local[/\\]temp|tmp)(/|\\\\)",
        suspicion_boost=0.2,
        tags=["filesystem", "temp"],
    ),
    TriageRule(
        rule_id="FS-005",
        name="Recently modified system file",
        description="System32/SysWOW64 path with a recorded modified timestamp.",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        condition_field="path",
        condition_operator="regex",
        condition_value=r"(?i)(windows[/\\]system32|windows[/\\]syswow64)",
        suspicion_boost=0.15,
        tags=["filesystem", "system", "modified"],
    ),
    # ── Registry ────────────────────────────────────────────────────────────
    TriageRule(
        rule_id="REG-001",
        name="Autorun Run key",
        description="Registry persistence via CurrentVersion\\Run.",
        category=ArtefactCategory.REGISTRY_KEY,
        condition_field="key_path",
        condition_operator="contains",
        condition_value="\\Run\\",
        suspicion_boost=0.35,
        tags=["registry", "persistence", "autorun"],
    ),
    TriageRule(
        rule_id="REG-002",
        name="Autorun RunOnce key",
        description="Registry persistence via CurrentVersion\\RunOnce.",
        category=ArtefactCategory.REGISTRY_KEY,
        condition_field="key_path",
        condition_operator="contains",
        condition_value="\\RunOnce",
        suspicion_boost=0.35,
        tags=["registry", "persistence", "autorun"],
    ),
    TriageRule(
        rule_id="REG-003",
        name="Service installation key",
        description="Registry key under Services indicating service install.",
        category=ArtefactCategory.REGISTRY_KEY,
        condition_field="key_path",
        condition_operator="contains",
        condition_value="\\Services\\",
        suspicion_boost=0.3,
        tags=["registry", "service"],
    ),
    TriageRule(
        rule_id="REG-004",
        name="Shell extension / Winlogon Shell",
        description="Winlogon Shell or Explorer shell extension persistence.",
        category=ArtefactCategory.REGISTRY_KEY,
        condition_field="key_path",
        condition_operator="regex",
        condition_value=r"(?i)Winlogon\\Shell|ShellIconOverlayIdentifiers|ShellExecuteHooks",
        suspicion_boost=0.35,
        tags=["registry", "shell", "persistence"],
    ),
    TriageRule(
        rule_id="REG-005",
        name="IFEO debugger key",
        description="Image File Execution Options debugger hijack.",
        category=ArtefactCategory.REGISTRY_KEY,
        condition_field="key_path",
        condition_operator="contains",
        condition_value="\\Image File Execution Options\\",
        suspicion_boost=0.45,
        tags=["registry", "ifeo", "debugger"],
    ),
    TriageRule(
        rule_id="REG-006",
        name="Disabled security setting",
        description="Registry value suggesting disabled Windows security features.",
        category=ArtefactCategory.REGISTRY_KEY,
        condition_field="value_name",
        condition_operator="regex",
        condition_value=r"(?i)(DisableAntiSpyware|DisableAntiVirus|EnableLUA|DisableRealtimeMonitoring|TamperProtection)",
        suspicion_boost=0.4,
        tags=["registry", "security", "defense_evasion"],
    ),
    # ── Browser ─────────────────────────────────────────────────────────────
    TriageRule(
        rule_id="BRW-001",
        name="Known phishing domain visit",
        description="Browser history URL matches common phishing domain patterns.",
        category=ArtefactCategory.BROWSER_HISTORY,
        condition_field="url",
        condition_operator="regex",
        condition_value=r"(?i)(paypal|apple|microsoft|amazon|bank).*(secure|login|verify|update).*\.(ru|cn|tk|top|xyz|pw)",
        suspicion_boost=0.4,
        tags=["browser", "phishing"],
    ),
    TriageRule(
        rule_id="BRW-002",
        name="Tor or proxy site visit",
        description="Visit to Tor (.onion) or known proxy/anonymiser services.",
        category=ArtefactCategory.BROWSER_HISTORY,
        condition_field="url",
        condition_operator="regex",
        condition_value=r"(?i)(\.onion\b|torproject\.org|proxysite\.com|hide\.me|vpn)",
        suspicion_boost=0.3,
        tags=["browser", "tor", "proxy"],
    ),
    TriageRule(
        rule_id="BRW-003",
        name="File download URL",
        description="Browser history URL points to a directly downloadable file.",
        category=ArtefactCategory.BROWSER_HISTORY,
        condition_field="url",
        condition_operator="regex",
        condition_value=r"(?i)\.(exe|msi|dll|ps1|bat|cmd|vbs|js|zip|rar|7z)(\?|$)",
        suspicion_boost=0.25,
        tags=["browser", "download"],
    ),
    # ── Event logs ──────────────────────────────────────────────────────────
    TriageRule(
        rule_id="EVT-001",
        name="Failed logon (4625)",
        description="Windows Security event 4625 — failed logon attempt.",
        category=ArtefactCategory.EVENT_LOG,
        condition_field="event_id",
        condition_operator="equals",
        condition_value=4625,
        suspicion_boost=0.35,
        tags=["event_log", "auth", "4625"],
    ),
    TriageRule(
        rule_id="EVT-002",
        name="Special privileges assigned (4672)",
        description="Windows Security event 4672 — privilege escalation indicator.",
        category=ArtefactCategory.EVENT_LOG,
        condition_field="event_id",
        condition_operator="equals",
        condition_value=4672,
        suspicion_boost=0.4,
        tags=["event_log", "privilege", "4672"],
    ),
    TriageRule(
        rule_id="EVT-003",
        name="Service installed (7045)",
        description="System event 7045 — new service installation.",
        category=ArtefactCategory.EVENT_LOG,
        condition_field="event_id",
        condition_operator="equals",
        condition_value=7045,
        suspicion_boost=0.35,
        tags=["event_log", "service", "7045"],
    ),
    TriageRule(
        rule_id="EVT-004",
        name="Audit log cleared (1102)",
        description="Security event 1102 — audit log cleared (anti-forensics).",
        category=ArtefactCategory.EVENT_LOG,
        condition_field="event_id",
        condition_operator="equals",
        condition_value=1102,
        suspicion_boost=0.5,
        tags=["event_log", "anti_forensics", "1102"],
    ),
    # ── Processes ───────────────────────────────────────────────────────────
    TriageRule(
        rule_id="PROC-001",
        name="Suspicious process name",
        description="Process name matches known offensive / dual-use tooling.",
        category=ArtefactCategory.RUNNING_PROCESS,
        condition_field="name",
        condition_operator="regex",
        condition_value=(
            r"(?i)\b("
            + "|".join(re.escape(name) for name in SUSPICIOUS_PROCESSES)
            + r")\b"
        ),
        suspicion_boost=0.45,
        tags=["process", "tooling"],
    ),
    TriageRule(
        rule_id="PROC-002",
        name="Process launched from temp directory",
        description="Command line references execution from a temp path.",
        category=ArtefactCategory.RUNNING_PROCESS,
        condition_field="command_line",
        condition_operator="regex",
        condition_value=r"(?i)(\\windows\\temp\\|\\appdata\\local\\temp\\|\\tmp\\)",
        suspicion_boost=0.35,
        tags=["process", "temp"],
    ),
    TriageRule(
        rule_id="PROC-003",
        name="Unusual parent-child relationship",
        description="Office/browser parent spawning scripting or cmd interpreters.",
        category=ArtefactCategory.RUNNING_PROCESS,
        condition_field="parent_name",
        condition_operator="regex",
        condition_value=r"(?i)(winword|excel|powerpnt|outlook|acrord32|chrome|msedge|firefox)\.exe$",
        suspicion_boost=0.3,
        tags=["process", "parent_child", "living_off_the_land"],
    ),
    TriageRule(
        rule_id="PROC-004",
        name="Scripting host child process",
        description="Process is a scripting host often abused in parent-child chains.",
        category=ArtefactCategory.RUNNING_PROCESS,
        condition_field="name",
        condition_operator="regex",
        condition_value=r"(?i)^(cmd|powershell|pwsh|wscript|cscript|mshta|rundll32)\.exe$",
        suspicion_boost=0.2,
        tags=["process", "scripting"],
    ),
    # ── Network ─────────────────────────────────────────────────────────────
    TriageRule(
        rule_id="NET-001",
        name="External network connection",
        description="Connection to a non-private remote address.",
        category=ArtefactCategory.NETWORK_CONNECTION,
        condition_field="is_external",
        condition_operator="equals",
        condition_value=True,
        suspicion_boost=0.25,
        tags=["network", "external"],
    ),
    TriageRule(
        rule_id="NET-002",
        name="Unusual remote port",
        description="Remote port matches known C2 / dual-use listener ports.",
        category=ArtefactCategory.NETWORK_CONNECTION,
        condition_field="remote_port",
        condition_operator="in_list",
        condition_value=list(EXTERNAL_PORT_INDICATORS),
        suspicion_boost=0.4,
        tags=["network", "port"],
    ),
    TriageRule(
        rule_id="NET-003",
        name="Unusual local listener port",
        description="Local port matches known suspicious listener ports.",
        category=ArtefactCategory.NETWORK_CONNECTION,
        condition_field="local_port",
        condition_operator="in_list",
        condition_value=list(EXTERNAL_PORT_INDICATORS),
        suspicion_boost=0.35,
        tags=["network", "listener"],
    ),
    TriageRule(
        rule_id="NET-004",
        name="Multi-connection process marker",
        description="Artefact metadata marks the owner PID as having many connections.",
        category=ArtefactCategory.NETWORK_CONNECTION,
        condition_field="connection_count",
        condition_operator="greater_than",
        condition_value=5,
        suspicion_boost=0.2,
        tags=["network", "multi_connection"],
    ),
    # ── Injected code ───────────────────────────────────────────────────────
    TriageRule(
        rule_id="INJ-001",
        name="Any injected code finding",
        description="Any malfind / injected-code artefact is treated as HIGH suspicion.",
        category=ArtefactCategory.INJECTED_CODE,
        condition_field="pid",
        condition_operator="greater_than",
        condition_value=-1,
        suspicion_boost=0.6,
        tags=["injection", "automatic_high"],
    ),
    TriageRule(
        rule_id="INJ-002",
        name="MZ header in injected region",
        description="Injected region contains an MZ/PE header indicator.",
        category=ArtefactCategory.INJECTED_CODE,
        condition_field="suspicious_indicators",
        condition_operator="contains",
        condition_value="MZ header",
        suspicion_boost=0.25,
        tags=["injection", "pe"],
    ),
    TriageRule(
        rule_id="INJ-003",
        name="RWX injected memory",
        description="Injected region reported with RWX or execute+write protection.",
        category=ArtefactCategory.INJECTED_CODE,
        condition_field="protection",
        condition_operator="regex",
        condition_value=r"(?i)(RWX|EXECUTE.*WRITE|WRITE.*EXECUTE)",
        suspicion_boost=0.2,
        tags=["injection", "rwx"],
    ),
]


def rules_for_category(category: ArtefactCategory) -> list[TriageRule]:
    """Return default triage rules applicable to ``category``."""
    return [rule for rule in DEFAULT_TRIAGE_RULES if rule.category is category]


def get_rule(rule_id: str) -> TriageRule | None:
    """Look up a default triage rule by ``rule_id``."""
    for rule in DEFAULT_TRIAGE_RULES:
        if rule.rule_id == rule_id:
            return rule
    return None
