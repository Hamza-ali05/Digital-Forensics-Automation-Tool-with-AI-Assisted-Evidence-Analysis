"""ACPO-compliant forensic audit logger and application logging setup."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from dfat.core.enums import HashAlgorithm, PipelineStage
from dfat.core.models.pipeline import AuditEntry
from dfat.infrastructure.logging.formatters import (
    HumanReadableFormatter,
    JSONLogFormatter,
)
from dfat.settings import LoggingSettings
from dfat.shared.hashing import compute_data_hash

_GENESIS_HASH = "0" * 64
_CHAIN_HASH_KEY = "_chain_hash"
_PREVIOUS_HASH_KEY = "_previous_hash"


class ForensicAuditLogger:
    """Append-only forensic audit trail with hash chaining.

    Each entry is written as a JSON line. Entry hashes chain to the previous
    entry hash to detect tampering (ACPO Principle 1 support).
    """

    def __init__(
        self,
        audit_log_path: Path,
        hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256,
    ) -> None:
        """Initialise the audit logger.

        Args:
            audit_log_path: Path to the append-only JSONL audit log.
            hash_algorithm: Algorithm used for entry hash chaining.
        """
        self._audit_log_path = audit_log_path
        self._hash_algorithm = hash_algorithm
        self._lock = threading.Lock()
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._audit_log_path.exists():
            self._audit_log_path.touch()

    def log_action(
        self,
        stage: PipelineStage,
        action: str,
        evidence_id: str,
        hash_before: Optional[str] = None,
        hash_after: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditEntry:
        """Append an audit entry for an evidence-related action.

        Args:
            stage: Pipeline stage associated with the action.
            action: Short action description.
            evidence_id: Related evidence identifier.
            hash_before: Optional integrity hash before the action.
            hash_after: Optional integrity hash after the action.
            details: Optional structured details.

        Returns:
            The persisted ``AuditEntry``.
        """
        with self._lock:
            previous_hash, next_number = self._read_tail_state()
            entry = AuditEntry(
                entry_number=next_number,
                timestamp=datetime.now(UTC),
                stage=stage,
                action=action,
                evidence_id=evidence_id,
                hash_before=hash_before,
                hash_after=hash_after,
                details=dict(details) if details is not None else {},
            )
            entry_hash = self._compute_entry_hash(entry, previous_hash)
            record = {
                "entry": entry.model_dump(mode="json"),
                _PREVIOUS_HASH_KEY: previous_hash,
                _CHAIN_HASH_KEY: entry_hash,
            }
            with self._audit_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str, ensure_ascii=True))
                handle.write("\n")
                handle.flush()
            return entry

    def flush(self) -> None:
        """Flush the on-disk audit log buffer."""
        with self._lock:
            if not self._audit_log_path.exists():
                return
            with self._audit_log_path.open("a", encoding="utf-8") as handle:
                handle.flush()
                os.fsync(handle.fileno())

    def get_audit_trail(self, evidence_id: str) -> list[AuditEntry]:
        """Return all audit entries for a given evidence identifier.

        Args:
            evidence_id: Evidence identifier to filter on.

        Returns:
            Matching audit entries in file order.
        """
        entries: list[AuditEntry] = []
        for record in self._iter_records():
            entry = AuditEntry.model_validate(record["entry"])
            if entry.evidence_id == evidence_id:
                entries.append(entry)
        return entries

    def verify_audit_integrity(self) -> bool:
        """Verify sequential numbering and unbroken hash chaining.

        Returns:
            True if the audit log is intact; otherwise False.
        """
        previous_hash = _GENESIS_HASH
        expected_number = 1
        for record in self._iter_records():
            try:
                entry = AuditEntry.model_validate(record["entry"])
                stored_previous = record.get(_PREVIOUS_HASH_KEY)
                stored_hash = record.get(_CHAIN_HASH_KEY)
            except Exception:
                return False
            if entry.entry_number != expected_number:
                return False
            if stored_previous != previous_hash:
                return False
            computed = self._compute_entry_hash(entry, previous_hash)
            if stored_hash != computed:
                return False
            previous_hash = computed
            expected_number += 1
        return True

    def _compute_entry_hash(self, entry: AuditEntry, previous_hash: str) -> str:
        """Compute the chain hash for an audit entry.

        Args:
            entry: Audit entry to hash.
            previous_hash: Hash of the previous entry (or genesis hash).

        Returns:
            Hexadecimal chain hash digest.
        """
        canonical = json.dumps(
            entry.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            ensure_ascii=True,
        )
        payload = f"{canonical}|{previous_hash}".encode("utf-8")
        return compute_data_hash(payload, self._hash_algorithm)

    def _read_tail_state(self) -> tuple[str, int]:
        """Read the last chain hash and next entry number.

        Returns:
            Tuple of ``(previous_hash, next_entry_number)``.
        """
        last_hash = _GENESIS_HASH
        next_number = 1
        for record in self._iter_records():
            last_hash = str(record.get(_CHAIN_HASH_KEY, _GENESIS_HASH))
            entry = record.get("entry", {})
            entry_number = int(entry.get("entry_number", 0))
            next_number = entry_number + 1
        return last_hash, next_number

    def _iter_records(self) -> list[dict[str, Any]]:
        """Load all JSONL audit records from disk.

        Returns:
            List of parsed record dictionaries.
        """
        if not self._audit_log_path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self._audit_log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                loaded = json.loads(stripped)
                if isinstance(loaded, dict):
                    records.append(loaded)
        return records


def setup_logging(settings: LoggingSettings) -> None:
    """Configure structlog and stdlib logging for the application.

    Args:
        settings: Logging configuration settings.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler()
    if settings.log_format.lower() == "json":
        handler.setFormatter(JSONLogFormatter())
    else:
        handler.setFormatter(HumanReadableFormatter())
    root.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
