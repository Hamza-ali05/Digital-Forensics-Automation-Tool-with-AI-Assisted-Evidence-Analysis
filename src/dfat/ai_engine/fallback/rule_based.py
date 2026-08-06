"""Rule-based AI triage fallback (no LLM dependency)."""

from __future__ import annotations

import ipaddress
from typing import Any

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact

_SUSPICIOUS_PROCESS_NAMES = frozenset(
    {
        "mimikatz.exe",
        "powershell.exe",
        "pwsh.exe",
        "cmd.exe",
        "wscript.exe",
        "cscript.exe",
        "mshta.exe",
        "rundll32.exe",
        "regsvr32.exe",
        "procdump.exe",
        "nc.exe",
        "ncat.exe",
    }
)

_SCORE_BY_LEVEL: dict[SuspicionLevel, float] = {
    SuspicionLevel.CRITICAL: 1.0,
    SuspicionLevel.HIGH: 0.8,
    SuspicionLevel.MEDIUM: 0.5,
    SuspicionLevel.LOW: 0.25,
    SuspicionLevel.INFORMATIONAL: 0.05,
}


class RuleBasedAnalyzer(IArtefactAnalyzer):
    """Keyword/heuristic triage used when the local LLM is unavailable."""

    @property
    def analyzer_name(self) -> str:
        """Return the stable analyser identifier."""
        return "RuleBasedFallback"

    def is_available(self) -> bool:
        """Return True — rule-based analysis is always available."""
        return True

    def analyze(self, artefact_set: ArtefactSet) -> list[RankedArtefact]:
        """Classify artefacts using deterministic heuristic rules.

        Args:
            artefact_set: Parsed artefacts pending triage.

        Returns:
            Ranked artefacts ordered by suspicion then score.
        """
        ranked = [self._classify_one(artefact) for artefact in artefact_set.artefacts]
        ranked.sort(
            key=lambda item: (
                -_SCORE_BY_LEVEL.get(item.suspicion_level, 0.0),
                -item.relevance_score,
            )
        )
        return ranked

    def summarize(self, ranked_artefacts: list[RankedArtefact]) -> str:
        """Generate a template-based summary without LLM dependency.

        Args:
            ranked_artefacts: Triaged artefacts.

        Returns:
            Human-readable template summary.
        """
        categories = {item.category for item in ranked_artefacts}
        critical_count = sum(
            1
            for item in ranked_artefacts
            if item.suspicion_level is SuspicionLevel.CRITICAL
        )
        high_count = sum(
            1 for item in ranked_artefacts if item.suspicion_level is SuspicionLevel.HIGH
        )
        return (
            f"Analysis identified {len(ranked_artefacts)} artefacts across "
            f"{len(categories)} categories. {critical_count} items flagged as "
            f"critical and {high_count} as high. "
            "This summary was produced by the rule-based fallback analyser "
            "(no LLM). Structured JSON remains the authoritative record."
        )

    def _classify_one(self, artefact: Artefact) -> RankedArtefact:
        """Apply heuristic rules to a single artefact."""
        level, reason = self._rule_level(artefact)
        return RankedArtefact(
            **artefact.model_dump(),
            suspicion_level=level,
            relevance_score=_SCORE_BY_LEVEL[level],
            classification_reasoning=reason,
        )

    def _rule_level(self, artefact: Artefact) -> tuple[SuspicionLevel, str]:
        """Return suspicion level and reason for an artefact."""
        raw = artefact.raw_data
        if artefact.category is ArtefactCategory.INJECTED_CODE:
            return SuspicionLevel.CRITICAL, "Injected code finding (malfind)"

        if artefact.category is ArtefactCategory.REGISTRY_KEY:
            key_path = str(raw.get("key_path", "")).lower()
            value_name = str(raw.get("value_name", "")).lower()
            joined = f"{key_path} {value_name}"
            if "runonce" in joined or "\\run" in joined or joined.endswith("run"):
                return SuspicionLevel.HIGH, "Autorun registry key (Run/RunOnce)"

        if artefact.category is ArtefactCategory.FILESYSTEM_METADATA:
            if bool(raw.get("is_deleted")):
                return SuspicionLevel.MEDIUM, "Deleted filesystem entry"

        if artefact.category is ArtefactCategory.RUNNING_PROCESS:
            name = str(raw.get("name", "")).lower()
            if name in _SUSPICIOUS_PROCESS_NAMES:
                return SuspicionLevel.HIGH, f"Suspicious process name: {name}"

        if artefact.category is ArtefactCategory.NETWORK_CONNECTION:
            if self._is_external_remote(raw):
                return SuspicionLevel.MEDIUM, "Network connection to external IP"

        return SuspicionLevel.INFORMATIONAL, "No elevated heuristic matched"

    @staticmethod
    def _is_external_remote(raw: dict[str, Any]) -> bool:
        """Return True if remote_address looks like a public IP."""
        remote = str(raw.get("remote_address", "")).split("%")[0].strip()
        if not remote or remote in {"0.0.0.0", "*", "::", "::0"}:
            return False
        # Strip port if present in combined fields.
        if remote.count(":") == 1 and remote.replace(".", "").replace(":", "").isdigit():
            remote = remote.split(":")[0]
        try:
            address = ipaddress.ip_address(remote)
        except ValueError:
            return False
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
        )
