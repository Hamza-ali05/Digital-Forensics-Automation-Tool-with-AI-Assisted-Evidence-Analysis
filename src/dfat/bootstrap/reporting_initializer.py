"""Reporting subsystem readiness checks for bootstrap."""

from __future__ import annotations

import importlib
import json
import logging
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.reporting.schema.schema_versions import get_schema_path
from dfat.settings import ReportingSettings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ReportingInitializer:
    """Verify report output paths, schema, templates, and PDF export deps."""

    def __init__(self, settings: ReportingSettings) -> None:
        """Initialise the reporting bootstrap helper.

        Args:
            settings: Reporting output and template configuration.
        """
        self._settings = settings

    async def initialize(self) -> PhaseResult:
        """Run reporting readiness checks.

        Returns:
            ``PhaseResult`` with ``COMPLETED`` or ``DEGRADED``.
        """
        started = time.perf_counter()
        details: dict[str, Any] = {}
        degraded: list[str] = []

        output_dir = self._resolve_path(self._settings.output_dir)
        output_ok = self._verify_output_dir_writable(output_dir)
        details["output_dir"] = str(output_dir)
        details["output_dir_writable"] = output_ok
        if not output_ok:
            degraded.append("report_output")

        schema_ok, schema_path = self._verify_schema()
        details["schema_path"] = str(schema_path) if schema_path else None
        details["schema_valid"] = schema_ok
        if not schema_ok:
            degraded.append("report_schema")

        template_ok, template_path = self._verify_narrative_template()
        details["template_path"] = str(template_path) if template_path else None
        details["template_renders"] = template_ok
        if not template_ok:
            degraded.append("narrative_template")

        pdf_ok, pdf_version = self._check_reportlab()
        details["reportlab_available"] = pdf_ok
        details["reportlab_version"] = pdf_version
        if not pdf_ok:
            degraded.append("pdf_export")
            logger.warning(
                "reportlab is not installed — PDF export degraded to plaintext fallback. "
                "Install with: pip install reportlab"
            )

        duration_ms = (time.perf_counter() - started) * 1000.0
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        message = (
            "Reporting system ready"
            if status == InitStatus.COMPLETED
            else f"Reporting degraded: {', '.join(degraded)}"
        )

        return PhaseResult(
            phase=InitPhase.REPORTING,
            status=status,
            duration_ms=duration_ms,
            message=message,
            details=details,
            is_critical=True,
            degraded_capabilities=degraded,
        )

    def _resolve_path(self, path: Path) -> Path:
        """Resolve relative paths against the project root."""
        if path.is_absolute():
            return path
        return (_PROJECT_ROOT / path).resolve()

    def _verify_output_dir_writable(self, output_dir: Path) -> bool:
        """Return whether ``output_dir`` can be created and written to."""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".dfat_report_write_test_",
                dir=str(output_dir),
                delete=False,
            ) as handle:
                handle.write("dfat reporting write probe\n")
                probe = Path(handle.name)
            probe.unlink(missing_ok=True)
            return True
        except OSError as exc:
            logger.error("Reporting output directory not writable: %s", exc)
            return False

    def _verify_schema(self) -> tuple[bool, Path | None]:
        """Verify the configured report schema file exists and parses."""
        try:
            schema_path = get_schema_path(self._settings.json_schema_version)
            if not schema_path.is_file():
                return False, schema_path
            with schema_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                return False, schema_path
            return True, schema_path
        except (KeyError, OSError, json.JSONDecodeError) as exc:
            logger.error("Report schema validation failed: %s", exc)
            return False, None

    def _verify_narrative_template(self) -> tuple[bool, Path | None]:
        """Verify the narrative Jinja template exists and renders."""
        template_dir = self._resolve_path(self._settings.template_dir)
        template_path = template_dir / "narrative_template.j2"
        if not template_path.is_file():
            logger.error("Narrative template missing: %s", template_path)
            return False, template_path

        try:
            env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=select_autoescape(enabled_extensions=()),
            )
            template = env.get_template("narrative_template.j2")
            rendered = template.render(
                case_name="Bootstrap Case",
                case_id="case-bootstrap",
                generated_at="2026-01-01T00:00:00+00:00",
                evidence_id="evidence-bootstrap",
                report_id="report-bootstrap",
                llm_model="bootstrap",
                confidence=0.5,
                prompt_version="1.0.0",
                disclaimer="DISCLAIMER: bootstrap probe",
                executive_summary="Bootstrap executive summary.",
                key_findings="None",
                key_findings_list=[],
                findings_by_category={},
                timeline=[],
                iocs=[],
                actions=[],
                statistics=SimpleNamespace(
                    by_category={"bootstrap": 0},
                    by_suspicion_level={"informational": 0},
                ),
                statistics_appendix="",
                generation_params={},
                artefact_count=0,
                investigator="Bootstrap",
            )
            return bool(rendered.strip()), template_path
        except Exception as exc:  # noqa: BLE001
            logger.error("Narrative template render failed: %s", exc)
            return False, template_path

    def _check_reportlab(self) -> tuple[bool, str | None]:
        """Return whether reportlab is importable and its version string."""
        try:
            module = importlib.import_module("reportlab")
        except ImportError:
            return False, None
        return True, str(getattr(module, "__version__", "unknown"))
