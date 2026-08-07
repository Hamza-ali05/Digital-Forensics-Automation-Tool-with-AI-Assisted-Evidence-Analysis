"""Artefact categorisation — validate category schemas and enrich sub-categories."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.parsers.eventlog import SECURITY_EVENT_IDS

logger = logging.getLogger(__name__)

# Required ``raw_data`` keys per category (parser contracts).
_CATEGORY_REQUIRED_KEYS: dict[ArtefactCategory, frozenset[str]] = {
    ArtefactCategory.FILESYSTEM_METADATA: frozenset(
        {"filename", "path", "size", "is_deleted", "file_type"}
    ),
    ArtefactCategory.REGISTRY_KEY: frozenset(
        {"hive_name", "key_path", "value_name", "value_data", "value_type"}
    ),
    ArtefactCategory.BROWSER_HISTORY: frozenset(
        {"url", "title", "visit_count", "browser_type"}
    ),
    ArtefactCategory.EVENT_LOG: frozenset(
        {"event_id", "message", "is_security_relevant"}
    ),
    ArtefactCategory.RUNNING_PROCESS: frozenset({"pid", "name"}),
    ArtefactCategory.NETWORK_CONNECTION: frozenset(
        {"protocol", "local_address", "remote_address", "is_external"}
    ),
    ArtefactCategory.INJECTED_CODE: frozenset(
        {"pid", "process_name", "vad_start", "protection", "suspicious_indicators"}
    ),
}

# Registry Run / autorun persistence locations (case-insensitive path match).
_AUTORUN_KEY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"CurrentVersion\\Run(Once(Ex)?|Services(Once)?)?(\\|$)",
        r"CurrentVersion\\Policies\\Explorer\\Run(\\|$)",
        r"Winlogon\\(Userinit|Shell)(\\|$)",
        r"Windows NT\\CurrentVersion\\Winlogon\\(Userinit|Shell)(\\|$)",
        r"CurrentVersion\\Explorer\\(User\s+)?Shell\s+Folders(\\|$)",
        r"CurrentVersion\\Explorer\\StartupApproved\\",
        r"Services\\[^\\]+\\ImagePath$",
    )
)


class ArtefactCategoriser:
    """Validate artefact category schemas and enrich with sub-categories.

    Adds ``sub_category`` (and related flags) to each artefact's ``metadata``
    dict. Does not drop artefacts; schema mismatches are recorded so downstream
    stages can decide how to handle them.
    """

    def categorise(self, artefact_set: ArtefactSet) -> ArtefactSet:
        """Validate and enrich every artefact in ``artefact_set``.

        Args:
            artefact_set: Parsed (typically normalised) artefact collection.

        Returns:
            New ``ArtefactSet`` with enriched ``metadata`` on each artefact and
            refreshed ``categories_present``.
        """
        enriched: list[Artefact] = []
        for artefact in artefact_set.artefacts:
            enriched.append(self._enrich(artefact))

        categories = sorted({item.category for item in enriched}, key=lambda c: c.value)
        return artefact_set.model_copy(
            update={
                "artefacts": enriched,
                "categories_present": categories,
            }
        )

    def _enrich(self, artefact: Artefact) -> Artefact:
        """Validate schema and attach ``sub_category`` metadata."""
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        schema_valid = self._schema_matches(artefact.category, raw)
        if not schema_valid:
            inferred = self._infer_category(raw)
            if inferred is not None and inferred is not artefact.category:
                logger.debug(
                    "Artefact %s category %s does not match raw_data; "
                    "schema resembles %s",
                    artefact.artefact_id,
                    artefact.category.value,
                    inferred.value,
                )

        sub_category = self._resolve_sub_category(artefact.category, raw)
        metadata = dict(artefact.metadata)
        metadata["schema_valid"] = schema_valid
        if sub_category is not None:
            metadata["sub_category"] = sub_category
        elif "sub_category" not in metadata:
            # Explicit null-equivalent omission: leave key absent unless set.
            pass

        return artefact.model_copy(update={"metadata": metadata})

    def _schema_matches(
        self,
        category: ArtefactCategory,
        raw_data: dict[str, Any],
    ) -> bool:
        """Return whether ``raw_data`` contains the required keys for ``category``."""
        required = _CATEGORY_REQUIRED_KEYS.get(category)
        if required is None:
            return True
        return required.issubset(raw_data.keys())

    def _infer_category(self, raw_data: dict[str, Any]) -> Optional[ArtefactCategory]:
        """Best-effort category inference from ``raw_data`` keys."""
        keys = frozenset(raw_data.keys())
        best: Optional[ArtefactCategory] = None
        best_score = 0
        for category, required in _CATEGORY_REQUIRED_KEYS.items():
            score = len(required & keys)
            if score == len(required) and score > best_score:
                best = category
                best_score = score
        return best

    def _resolve_sub_category(
        self,
        category: ArtefactCategory,
        raw_data: dict[str, Any],
    ) -> Optional[str]:
        """Derive a forensic sub-category label when applicable."""
        if category is ArtefactCategory.REGISTRY_KEY:
            if self._is_autorun_key(raw_data):
                return "autorun_key"
            if str(raw_data.get("source", "")).lower() == "memory":
                return "memory_hive_key"
            return None

        if category is ArtefactCategory.EVENT_LOG:
            if self._is_security_event(raw_data):
                return "security_event"
            return None

        if category is ArtefactCategory.NETWORK_CONNECTION:
            if raw_data.get("is_external") is True:
                return "external_connection"
            return "local_connection"

        if category is ArtefactCategory.FILESYSTEM_METADATA:
            if raw_data.get("is_deleted") is True:
                return "deleted_file"
            file_type = str(raw_data.get("file_type", "")).lower()
            if file_type == "directory":
                return "directory_entry"
            return None

        if category is ArtefactCategory.INJECTED_CODE:
            indicators = raw_data.get("suspicious_indicators") or []
            if isinstance(indicators, list) and indicators:
                return "suspicious_injection"
            return "vad_anomaly"

        if category is ArtefactCategory.BROWSER_HISTORY:
            browser = str(raw_data.get("browser_type", "")).lower()
            if browser in {"chrome", "firefox", "edge"}:
                return f"{browser}_history"
            return None

        if category is ArtefactCategory.RUNNING_PROCESS:
            return None

        return None

    @staticmethod
    def _is_autorun_key(raw_data: dict[str, Any]) -> bool:
        """Return ``True`` for Windows Run / autorun persistence keys."""
        key_path = str(raw_data.get("key_path", "") or "")
        if not key_path:
            return False
        normalised = key_path.replace("/", "\\")
        return any(pattern.search(normalised) for pattern in _AUTORUN_KEY_PATTERNS)

    @staticmethod
    def _is_security_event(raw_data: dict[str, Any]) -> bool:
        """Return ``True`` for security-relevant Windows event log entries."""
        if raw_data.get("is_security_relevant") is True:
            return True
        event_id = raw_data.get("event_id")
        try:
            return int(event_id) in SECURITY_EVENT_IDS
        except (TypeError, ValueError):
            return False
