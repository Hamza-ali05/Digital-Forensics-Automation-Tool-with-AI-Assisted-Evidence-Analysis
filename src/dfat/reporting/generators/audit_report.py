"""Audit trail report generation for forensic pipeline documentation."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import AuditEntry
from dfat.services.audit_service import AuditService

_INTEGRITY_ACTION_RE = re.compile(
    r"(integrity|verify.?hash|hash.?verif|custody.?verif|hash_set)",
    re.IGNORECASE,
)


class AuditTrailReport(BaseModel):
    """Comprehensive audit trail report for an evidence item / pipeline job."""

    model_config = ConfigDict(frozen=False)

    evidence_id: str
    pipeline_job_id: Optional[str] = None
    total_entries: int = 0
    entries_by_stage: dict[str, int] = Field(default_factory=dict)
    entries: list[AuditEntry] = Field(default_factory=list)
    earliest_action: datetime
    latest_action: datetime
    users_involved: list[str] = Field(default_factory=list)
    integrity_events: list[AuditEntry] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditReportGenerator:
    """Build text/CSV audit trail reports from ``AuditService`` entries."""

    def __init__(self, audit_service: AuditService) -> None:
        """Initialise the generator.

        Args:
            audit_service: Dual-write forensic audit service.
        """
        self._audit_service = audit_service

    async def generate(
        self,
        evidence_id: str,
        pipeline_job_id: Optional[str] = None,
    ) -> AuditTrailReport:
        """Generate an audit trail report for evidence (optionally one job).

        Args:
            evidence_id: Evidence identifier to load audit entries for.
            pipeline_job_id: Optional pipeline job ID filter (``job_id`` /
                ``pipeline_job_id`` in entry details).

        Returns:
            Aggregated ``AuditTrailReport``.
        """
        entries = await self._audit_service.get_audit_trail(evidence_id)
        if pipeline_job_id:
            entries = [
                entry
                for entry in entries
                if self._matches_job(entry, pipeline_job_id)
            ]

        entries = sorted(entries, key=lambda item: (item.timestamp, item.entry_number))
        now = datetime.now(UTC)
        if entries:
            earliest = entries[0].timestamp
            latest = entries[-1].timestamp
        else:
            earliest = now
            latest = now

        stage_counts = Counter(
            entry.stage.value if isinstance(entry.stage, PipelineStage) else str(entry.stage)
            for entry in entries
        )
        # Ensure all pipeline stages appear with zero when absent.
        entries_by_stage = {stage.value: 0 for stage in PipelineStage}
        entries_by_stage.update(dict(stage_counts))

        users = sorted(
            {
                user
                for entry in entries
                if (user := self._extract_user(entry)) is not None
            }
        )
        integrity_events = [entry for entry in entries if self._is_integrity_event(entry)]

        return AuditTrailReport(
            evidence_id=evidence_id,
            pipeline_job_id=pipeline_job_id,
            total_entries=len(entries),
            entries_by_stage=entries_by_stage,
            entries=list(entries),
            earliest_action=earliest,
            latest_action=latest,
            users_involved=users,
            integrity_events=integrity_events,
            generated_at=now,
        )

    async def export_text(self, report: AuditTrailReport) -> str:
        """Render the audit trail report as formatted plain text.

        Args:
            report: Audit trail report to render.

        Returns:
            Multi-section plain-text document.
        """
        lines: list[str] = [
            "=" * 72,
            "DFAT AUDIT TRAIL REPORT",
            "=" * 72,
            f"Evidence ID:        {report.evidence_id}",
            f"Pipeline job ID:    {report.pipeline_job_id or '(all jobs)'}",
            f"Total entries:      {report.total_entries}",
            f"Earliest action:    {report.earliest_action.isoformat()}",
            f"Latest action:      {report.latest_action.isoformat()}",
            f"Generated at (UTC): {report.generated_at.isoformat()}",
            "",
            "-" * 72,
            "ACTIONS PER PIPELINE STAGE",
            "-" * 72,
        ]
        for stage, count in sorted(report.entries_by_stage.items()):
            lines.append(f"  {stage}: {count}")

        lines.extend(
            [
                "",
                "-" * 72,
                "USERS INVOLVED",
                "-" * 72,
            ]
        )
        if report.users_involved:
            for user in report.users_involved:
                lines.append(f"  - {user}")
        else:
            lines.append("  (none recorded)")

        lines.extend(
            [
                "",
                "-" * 72,
                f"INTEGRITY VERIFICATION EVENTS ({len(report.integrity_events)})",
                "-" * 72,
            ]
        )
        if report.integrity_events:
            for entry in report.integrity_events:
                lines.append(self._format_entry_line(entry))
        else:
            lines.append("  (none)")

        lines.extend(
            [
                "",
                "-" * 72,
                "COMPLETE AUDIT TIMELINE",
                "-" * 72,
            ]
        )
        if report.entries:
            for entry in report.entries:
                lines.append(self._format_entry_line(entry))
        else:
            lines.append("  (no audit entries)")

        lines.extend(
            [
                "",
                "=" * 72,
                "End of audit trail report.",
                "=" * 72,
            ]
        )
        return "\n".join(lines)

    async def export_csv(self, report: AuditTrailReport) -> str:
        """Export audit entries as CSV (RFC-compatible via ``csv`` module).

        Args:
            report: Audit trail report to export.

        Returns:
            CSV string with header row and one row per audit entry.
        """
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            [
                "entry_number",
                "timestamp",
                "stage",
                "action",
                "evidence_id",
                "user_id",
                "pipeline_job_id",
                "hash_before",
                "hash_after",
                "details",
            ]
        )
        for entry in report.entries:
            stage = (
                entry.stage.value
                if isinstance(entry.stage, PipelineStage)
                else str(entry.stage)
            )
            details = entry.details or {}
            writer.writerow(
                [
                    entry.entry_number,
                    entry.timestamp.isoformat(),
                    stage,
                    entry.action,
                    entry.evidence_id,
                    self._extract_user(entry) or "",
                    details.get("job_id")
                    or details.get("pipeline_job_id")
                    or report.pipeline_job_id
                    or "",
                    entry.hash_before or "",
                    entry.hash_after or "",
                    self._details_as_csv_field(details),
                ]
            )
        return buffer.getvalue()

    @staticmethod
    def _matches_job(entry: AuditEntry, pipeline_job_id: str) -> bool:
        """Return True when entry details reference the given job ID."""
        details = entry.details or {}
        candidates = {
            str(details.get("job_id") or ""),
            str(details.get("pipeline_job_id") or ""),
            str(details.get("pipeline_id") or ""),
        }
        return pipeline_job_id in candidates

    @staticmethod
    def _extract_user(entry: AuditEntry) -> Optional[str]:
        """Extract acting user ID from entry details when present."""
        details = entry.details or {}
        for key in ("user_id", "performed_by_user_id", "actor_user_id"):
            value = details.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _is_integrity_event(entry: AuditEntry) -> bool:
        """Identify integrity / hash verification related audit actions."""
        if entry.hash_before or entry.hash_after:
            return True
        if _INTEGRITY_ACTION_RE.search(entry.action or ""):
            return True
        details = entry.details or {}
        for key in details:
            if "integrity" in str(key).lower() or "hash" in str(key).lower():
                return True
        return False

    @staticmethod
    def _format_entry_line(entry: AuditEntry) -> str:
        """Format a single audit entry for the text timeline."""
        stage = (
            entry.stage.value
            if isinstance(entry.stage, PipelineStage)
            else str(entry.stage)
        )
        user = AuditReportGenerator._extract_user(entry) or "-"
        return (
            f"  [{entry.entry_number}] {entry.timestamp.isoformat()} | "
            f"{stage} | {entry.action} | user={user}"
        )

    @staticmethod
    def _details_as_csv_field(details: dict[str, Any]) -> str:
        """Serialise details dict to a compact CSV-safe string."""
        if not details:
            return ""
        parts: list[str] = []
        for key in sorted(details.keys()):
            parts.append(f"{key}={details[key]}")
        return "; ".join(parts)
