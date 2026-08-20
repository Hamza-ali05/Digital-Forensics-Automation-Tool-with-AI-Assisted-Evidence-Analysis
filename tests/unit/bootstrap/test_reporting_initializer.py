"""Unit tests for ReportingInitializer."""

from __future__ import annotations

from pathlib import Path

import pytest

from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.bootstrap.reporting_initializer import ReportingInitializer
from dfat.settings import ReportingSettings


@pytest.mark.asyncio
async def test_initialize_completes_with_valid_reporting_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "outputs"
    settings = ReportingSettings(
        output_dir=output_dir,
        json_schema_version="1.0.0",
        template_dir=Path("src/dfat/reporting/templates"),
    )
    initializer = ReportingInitializer(settings)
    monkeypatch.setattr(initializer, "_check_reportlab", lambda: (True, "4.0.0"))
    result = await initializer.initialize()

    assert result.phase == InitPhase.REPORTING
    assert result.status == InitStatus.COMPLETED
    assert result.details["output_dir_writable"] is True
    assert result.details["schema_valid"] is True
    assert result.details["template_renders"] is True
    assert result.details["reportlab_available"] is True
    assert result.degraded_capabilities == []


@pytest.mark.asyncio
async def test_pdf_fallback_noted_when_reportlab_missing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "outputs"
    settings = ReportingSettings(
        output_dir=output_dir,
        json_schema_version="1.0.0",
        template_dir=Path("src/dfat/reporting/templates"),
    )
    initializer = ReportingInitializer(settings)
    monkeypatch.setattr(initializer, "_check_reportlab", lambda: (False, None))
    result = await initializer.initialize()

    assert result.status == InitStatus.DEGRADED
    assert "pdf_export" in result.degraded_capabilities
    assert result.details["reportlab_available"] is False
    assert any("PDF export degraded" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_invalid_schema_marks_reporting_degraded(tmp_path: Path) -> None:
    settings = ReportingSettings(
        output_dir=tmp_path / "outputs",
        json_schema_version="9.9.9",
        template_dir=Path("src/dfat/reporting/templates"),
    )
    result = await ReportingInitializer(settings).initialize()
    assert result.status == InitStatus.DEGRADED
    assert "report_schema" in result.degraded_capabilities
