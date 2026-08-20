"""Console and JSON presentation for bootstrap startup reports."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from dfat.bootstrap.models import InitPhase, InitStatus, StartupReport, SystemReadiness

logger = logging.getLogger(__name__)

_PHASE_LABELS: dict[InitPhase, str] = {
    InitPhase.CONFIGURATION: "Configuration",
    InitPhase.DIRECTORIES: "Directories",
    InitPhase.DATABASE: "Database",
    InitPhase.AUTHENTICATION: "Authentication",
    InitPhase.AUDIT_LOGGING: "Audit Logging",
    InitPhase.FORENSIC_PARSERS: "Forensic Parsers",
    InitPhase.DATASET_DISCOVERY: "Datasets",
    InitPhase.KNOWLEDGE_BASE: "Knowledge Base",
    InitPhase.IOC_DATABASE: "IOC Database",
    InitPhase.THREAT_INTELLIGENCE: "Threat Intel",
    InitPhase.ML_MODELS: "ML Models",
    InitPhase.LLM_SERVICE: "AI/LLM Service",
    InitPhase.RAG_PIPELINE: "RAG Pipeline",
    InitPhase.REPORTING: "Reporting",
    InitPhase.EVALUATION: "Evaluation",
    InitPhase.BACKGROUND_WORKERS: "Background Tasks",
}

_STATUS_DISPLAY: dict[InitStatus, str] = {
    InitStatus.COMPLETED: "OK",
    InitStatus.DEGRADED: "DEGRADED",
    InitStatus.FAILED: "FAILED",
    InitStatus.SKIPPED: "SKIPPED",
    InitStatus.PENDING: "PENDING",
    InitStatus.RUNNING: "RUNNING",
}

_BOX_WIDTH = 48


class StartupReportPrinter:
    """Format and emit startup diagnostics to the console and filesystem."""

    def __init__(
        self,
        *,
        api_base: str = "http://localhost:8000/api/v1",
        docs_url: str = "http://localhost:8000/docs",
        frontend_url: str = "http://localhost:3000",
    ) -> None:
        self._api_base = api_base
        self._docs_url = docs_url
        self._frontend_url = frontend_url

    def print_report(self, report: StartupReport) -> None:
        """Print a formatted startup banner to the console."""
        lines = self._format_banner(report)
        banner = "\n".join(lines)
        print(banner)
        logger.info("Startup report printed (status=%s)", report.system_status.value)

    def save_report(self, report: StartupReport, path: Path) -> None:
        """Persist the startup report as JSON for programmatic access."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json")
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info("Startup report saved to %s", target)

    def _format_banner(self, report: StartupReport) -> list[str]:
        width = _BOX_WIDTH
        inner = width - 2  # between ║ … ║
        lines: list[str] = []

        def row(text: str) -> str:
            content = f"  {text}"
            if len(content) > inner:
                content = content[: inner - 1] + "…"
            return "║" + content.ljust(inner) + "║"

        def sep() -> str:
            return "╠" + ("═" * inner) + "╣"

        lines.append("╔" + ("═" * inner) + "╗")
        lines.append(row("DFAT — Digital Forensics Automation Tool"))
        lines.append(row(f"Version: {report.version}"))
        lines.append(row(f"Environment: {report.environment}"))
        lines.append(sep())
        lines.append(row(f"System Status: {report.system_status.value.upper()}"))
        seconds = report.total_duration_ms / 1000.0
        lines.append(row(f"Startup Time: {seconds:.1f} seconds"))
        lines.append(sep())

        for phase_result in report.phases:
            lines.append(row(self._format_phase_line(phase_result)))

        if report.critical_failures:
            lines.append(sep())
            lines.append(row("Critical failures:"))
            for failure in report.critical_failures:
                lines.append(row(f"  ✗ {failure}"))

        lines.append(sep())
        lines.append(row(f"API: {self._api_base}"))
        lines.append(row(f"Docs: {self._docs_url}"))
        lines.append(row(f"Frontend: {self._frontend_url}"))
        lines.append("╚" + ("═" * inner) + "╝")
        return lines

    def _format_phase_line(self, result: Any) -> str:
        label = _PHASE_LABELS.get(result.phase, result.phase.value)
        status = _STATUS_DISPLAY.get(result.status, result.status.value.upper())
        mark = "✓" if result.status in (InitStatus.COMPLETED, InitStatus.DEGRADED) else "✗"
        duration = self._format_duration(result.duration_ms)
        extra = self._phase_extra(result)

        base = f"{mark} {label:<18} {status:<8} ({duration}"
        if extra:
            base = f"{base}, {extra})"
        else:
            base = f"{base})"
        return base

    @staticmethod
    def _format_duration(duration_ms: float) -> str:
        if duration_ms >= 1000.0:
            return f"{duration_ms / 1000.0:.1f}s"
        return f"{duration_ms:.0f}ms"

    @staticmethod
    def _phase_extra(result: Any) -> Optional[str]:
        details = result.details or {}
        if result.phase == InitPhase.FORENSIC_PARSERS:
            parsers = details.get("parsers") or {}
            if isinstance(parsers, dict) and parsers:
                available = sum(
                    1 for info in parsers.values() if info.get("available")
                )
                return f"{available}/{len(parsers)} available"
        if result.phase == InitPhase.DATASET_DISCOVERY:
            total = details.get("total_discovered")
            if total is not None:
                return f"{total} found"
        if result.phase == InitPhase.LLM_SERVICE and result.status == InitStatus.DEGRADED:
            return "fallback mode"
        if result.status == InitStatus.DEGRADED and result.degraded_capabilities:
            return "degraded"
        return None
