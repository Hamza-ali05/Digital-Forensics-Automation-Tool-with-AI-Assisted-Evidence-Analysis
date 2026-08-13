"""Unit tests for audit trail report generation (Prompt 6.9)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import AuditEntry
from dfat.reporting.generators.audit_report import (
    AuditReportGenerator,
    AuditTrailReport,
)
from dfat.services.audit_service import AuditService


def _entries() -> list[AuditEntry]:
    t0 = datetime.now(UTC) - timedelta(hours=3)
    t1 = datetime.now(UTC) - timedelta(hours=2)
    t2 = datetime.now(UTC) - timedelta(hours=1)
    t3 = datetime.now(UTC) - timedelta(minutes=30)
    return [
        AuditEntry(
            entry_number=1,
            timestamp=t0,
            stage=PipelineStage.ACQUISITION,
            action="EVIDENCE_LOADED",
            evidence_id="ev-audit-1",
            details={"user_id": "alice", "job_id": "job-A"},
        ),
        AuditEntry(
            entry_number=2,
            timestamp=t1,
            stage=PipelineStage.ACQUISITION,
            action="INTEGRITY_VERIFIED",
            evidence_id="ev-audit-1",
            hash_before="a" * 64,
            hash_after="a" * 64,
            details={"user_id": "alice", "job_id": "job-A"},
        ),
        AuditEntry(
            entry_number=3,
            timestamp=t2,
            stage=PipelineStage.PARSING,
            action="PARSING_STARTED",
            evidence_id="ev-audit-1",
            details={"user_id": "bob", "job_id": "job-A"},
        ),
        AuditEntry(
            entry_number=4,
            timestamp=t3,
            stage=PipelineStage.REPORTING,
            action="REPORT_GENERATED",
            evidence_id="ev-audit-1",
            details={"user_id": "bob", "job_id": "job-B"},
        ),
    ]


@pytest.mark.asyncio
async def test_generate_includes_all_entries_grouped_by_stage() -> None:
    """Verify report includes all entries and groups counts by stage."""
    audit_service = MagicMock(spec=AuditService)
    audit_service.get_audit_trail = AsyncMock(return_value=_entries())
    generator = AuditReportGenerator(audit_service)

    report = await generator.generate("ev-audit-1")

    assert isinstance(report, AuditTrailReport)
    assert report.evidence_id == "ev-audit-1"
    assert report.total_entries == 4
    assert len(report.entries) == 4
    assert report.entries_by_stage[PipelineStage.ACQUISITION.value] == 2
    assert report.entries_by_stage[PipelineStage.PARSING.value] == 1
    assert report.entries_by_stage[PipelineStage.REPORTING.value] == 1
    assert report.entries_by_stage[PipelineStage.AI_TRIAGE.value] == 0
    assert report.users_involved == ["alice", "bob"]
    assert len(report.integrity_events) == 1
    assert report.integrity_events[0].action == "INTEGRITY_VERIFIED"
    assert report.earliest_action <= report.latest_action


@pytest.mark.asyncio
async def test_generate_filters_by_pipeline_job_id() -> None:
    """Verify optional pipeline_job_id filters entries via details.job_id."""
    audit_service = MagicMock(spec=AuditService)
    audit_service.get_audit_trail = AsyncMock(return_value=_entries())
    generator = AuditReportGenerator(audit_service)

    report = await generator.generate("ev-audit-1", pipeline_job_id="job-A")

    assert report.pipeline_job_id == "job-A"
    assert report.total_entries == 3
    assert all(
        (e.details or {}).get("job_id") == "job-A" for e in report.entries
    )
    assert report.entries_by_stage[PipelineStage.REPORTING.value] == 0


@pytest.mark.asyncio
async def test_export_csv_is_valid() -> None:
    """Verify CSV export parses with the standard library csv reader."""
    audit_service = MagicMock(spec=AuditService)
    audit_service.get_audit_trail = AsyncMock(return_value=_entries())
    generator = AuditReportGenerator(audit_service)
    report = await generator.generate("ev-audit-1")

    csv_text = await generator.export_csv(report)
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    assert reader.fieldnames is not None
    assert "entry_number" in reader.fieldnames
    assert "stage" in reader.fieldnames
    assert "action" in reader.fieldnames
    assert len(rows) == 4
    assert rows[0]["action"] == "EVIDENCE_LOADED"
    assert rows[1]["action"] == "INTEGRITY_VERIFIED"
    assert rows[3]["pipeline_job_id"] == "job-B"


@pytest.mark.asyncio
async def test_export_text_includes_timeline() -> None:
    """Verify text export includes stage summary and timeline entries."""
    audit_service = MagicMock(spec=AuditService)
    audit_service.get_audit_trail = AsyncMock(return_value=_entries())
    generator = AuditReportGenerator(audit_service)
    report = await generator.generate("ev-audit-1")
    text = await generator.export_text(report)

    assert "AUDIT TRAIL REPORT" in text
    assert "ACTIONS PER PIPELINE STAGE" in text
    assert "acquisition: 2" in text
    assert "COMPLETE AUDIT TIMELINE" in text
    assert "INTEGRITY_VERIFIED" in text
    assert "alice" in text and "bob" in text
