"""Self-contained HTML forensic report exporter."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from jinja2 import Environment, FileSystemLoader, select_autoescape

from dfat import __version__
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact
from dfat.core.models.case import Case
from dfat.core.models.report import ForensicReport

_SUSPICION_RANK: dict[str, int] = {
    SuspicionLevel.CRITICAL.value: 0,
    SuspicionLevel.HIGH.value: 1,
    SuspicionLevel.MEDIUM.value: 2,
    SuspicionLevel.LOW.value: 3,
    SuspicionLevel.INFORMATIONAL.value: 4,
}

_ROW_CLASS: dict[str, str] = {
    SuspicionLevel.CRITICAL.value: "row-critical",
    SuspicionLevel.HIGH.value: "row-high",
    SuspicionLevel.MEDIUM.value: "row-medium",
    SuspicionLevel.LOW.value: "row-low",
    SuspicionLevel.INFORMATIONAL.value: "row-informational",
}


class HTMLReportExporter:
    """Render a self-contained HTML report (inline CSS/JS, no CDN)."""

    def __init__(self, output_dir: Path, template_dir: Path) -> None:
        """Initialise the HTML exporter.

        Args:
            output_dir: Directory for generated HTML files.
            template_dir: Directory containing ``html_report.j2``.
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._template_dir = Path(template_dir)
        self._env = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=select_autoescape(enabled_extensions=("html", "xml", "j2")),
        )

    def export(self, report: ForensicReport, case: Case) -> Path:
        """Render ``html_report.j2`` into a self-contained HTML file.

        Args:
            report: Combined dual-output forensic report.
            case: Full case lifecycle model for header/custody context.

        Returns:
            Path to the generated ``.html`` file.
        """
        ranked = self._ranked_from_report(report)
        stats = self._compute_statistics(ranked)
        narrative = report.narrative_report.summary_text or ""
        template = self._env.get_template("html_report.j2")
        rendered = template.render(
            case_name=case.case_name,
            case_id=case.case_id,
            case_status=str(getattr(case.status, "value", case.status)),
            investigator=case.metadata.investigator,
            lead_investigator=case.lead_investigator_id or case.metadata.investigator,
            evidence_count=case.evidence_count,
            case_tags=list(case.tags or []),
            report_id=report.report_id,
            evidence_id=report.json_report.evidence_id,
            tool_version=__version__,
            generated_at=report.json_report.generated_at.isoformat(),
            integrity_hash=report.json_report.integrity_hash,
            schema_version=report.json_report.schema_version,
            executive_summary=self._executive_summary(narrative),
            artefact_table_html=self._build_artefact_table(ranked),
            timeline_items=self._timeline_items(narrative, report),
            iocs=self._iocs(report, narrative),
            statistics_html=self._build_statistics_section(stats),
            custody_entries=int(
                (report.audit_metadata or {}).get("custody_chain_entries") or 0
            ),
            audit_user=(report.audit_metadata or {}).get(
                "generated_by_user_id", "system"
            ),
            pipeline_job_id=(report.audit_metadata or {}).get("pipeline_job_id", ""),
            generation_host=(report.audit_metadata or {}).get("generation_host", ""),
            linked_evidence=", ".join(case.evidence_ids) or report.json_report.evidence_id,
            disclaimer=self._disclaimer(narrative, report),
            json_payload=json.dumps(
                {
                    "report_id": report.report_id,
                    "evidence_id": report.json_report.evidence_id,
                    "integrity_hash": report.json_report.integrity_hash,
                    "artefacts": report.json_report.artefact_data,
                },
                indent=2,
                default=str,
            ),
        )

        safe_case = re.sub(r"[^\w\-]+", "_", case.case_name).strip("_") or "case"
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = (
            self._output_dir
            / f"dfat_report_{safe_case}_{report.report_id[:8]}_{stamp}.html"
        )
        path.write_text(rendered, encoding="utf-8")
        return path

    def _build_artefact_table(
        self,
        ranked: Sequence[Union[RankedArtefact, dict[str, Any]]],
    ) -> str:
        """Build a colour-coded, sortable HTML findings table.

        Args:
            ranked: Ranked artefacts or serialised artefact dictionaries.

        Returns:
            HTML table markup string.
        """
        rows: list[str] = [
            '<table class="data" id="findings-table">',
            "<thead><tr>"
            '<th data-numeric="0">ID</th>'
            '<th data-numeric="0">Category</th>'
            '<th data-numeric="1">Suspicion</th>'
            '<th data-numeric="1">Score</th>'
            '<th data-numeric="0">Summary</th>'
            "</tr></thead>",
            "<tbody>",
        ]
        ordered = sorted(ranked, key=self._sort_key)
        for item in ordered:
            artefact_id, category, suspicion, score, summary = self._row_fields(item)
            css = _ROW_CLASS.get(suspicion, "row-informational")
            badge = f"badge-{suspicion}" if suspicion in _ROW_CLASS else "badge-informational"
            rank = _SUSPICION_RANK.get(suspicion, 99)
            rows.append(
                f'<tr class="{css}">'
                f"<td>{html.escape(artefact_id)}</td>"
                f"<td>{html.escape(category)}</td>"
                f'<td data-sort="{rank}">'
                f'<span class="badge {badge}">{html.escape(suspicion)}</span></td>'
                f'<td data-sort="{score:.4f}">{score:.2f}</td>'
                f"<td>{html.escape(summary)}</td>"
                f"</tr>"
            )
        if not ordered:
            rows.append(
                '<tr><td colspan="5">No ranked artefacts available.</td></tr>'
            )
        rows.extend(["</tbody>", "</table>"])
        return "\n".join(rows)

    def _build_statistics_section(self, stats: dict[str, Any]) -> str:
        """Build HTML tables for category and suspicion counts.

        Args:
            stats: Mapping with ``by_category`` and ``by_suspicion_level``.

        Returns:
            HTML markup for statistics tables.
        """
        by_category = dict(stats.get("by_category") or {})
        by_level = dict(stats.get("by_suspicion_level") or {})
        parts = [
            f"<p><strong>Total artefacts:</strong> {int(stats.get('total_artefacts', 0))}</p>",
            "<h3>By category</h3>",
            self._simple_count_table("Category", by_category),
            "<h3>By suspicion level</h3>",
            self._simple_count_table("Suspicion level", by_level),
        ]
        return "\n".join(parts)

    @staticmethod
    def _simple_count_table(label: str, counts: dict[str, int]) -> str:
        """Render a two-column count table."""
        lines = [
            '<table class="data">',
            f"<thead><tr><th>{html.escape(label)}</th>"
            '<th data-numeric="1">Count</th></tr></thead><tbody>',
        ]
        for key, value in sorted(counts.items()):
            lines.append(
                f"<tr><td>{html.escape(str(key))}</td>"
                f'<td data-sort="{int(value)}">{int(value)}</td></tr>'
            )
        if not counts:
            lines.append('<tr><td colspan="2">No data</td></tr>')
        lines.extend(["</tbody>", "</table>"])
        return "\n".join(lines)

    def _ranked_from_report(self, report: ForensicReport) -> list[RankedArtefact]:
        """Best-effort conversion of serialised artefacts to ``RankedArtefact``."""
        ranked: list[RankedArtefact] = []
        for row in report.json_report.artefact_data or []:
            if not isinstance(row, dict):
                continue
            try:
                category = ArtefactCategory(str(row.get("category")))
            except ValueError:
                category = ArtefactCategory.FILESYSTEM_METADATA
            try:
                suspicion = SuspicionLevel(str(row.get("suspicion_level") or "informational"))
            except ValueError:
                suspicion = SuspicionLevel.INFORMATIONAL
            ranked.append(
                RankedArtefact(
                    artefact_id=str(row.get("artefact_id") or ""),
                    category=category,
                    source_evidence_id=report.json_report.evidence_id,
                    raw_data=dict(row.get("raw_data") or {}),
                    source_path=row.get("source_path"),
                    metadata=dict(row.get("metadata") or {}),
                    suspicion_level=suspicion,
                    relevance_score=float(row.get("relevance_score") or 0.0),
                    classification_reasoning=row.get("classification_reasoning"),
                )
            )
        return ranked

    @staticmethod
    def _compute_statistics(ranked: Sequence[RankedArtefact]) -> dict[str, Any]:
        """Count artefacts by category and suspicion level."""
        by_category = {category.value: 0 for category in ArtefactCategory}
        by_level = {level.value: 0 for level in SuspicionLevel}
        for artefact in ranked:
            by_category[artefact.category.value] = (
                by_category.get(artefact.category.value, 0) + 1
            )
            by_level[artefact.suspicion_level.value] = (
                by_level.get(artefact.suspicion_level.value, 0) + 1
            )
        return {
            "total_artefacts": len(ranked),
            "by_category": by_category,
            "by_suspicion_level": by_level,
        }

    @staticmethod
    def _sort_key(item: Union[RankedArtefact, dict[str, Any]]) -> tuple[int, float]:
        """Sort by suspicion rank then descending score."""
        if isinstance(item, RankedArtefact):
            return (
                _SUSPICION_RANK.get(item.suspicion_level.value, 99),
                -float(item.relevance_score),
            )
        level = str(item.get("suspicion_level") or "").lower()
        return (_SUSPICION_RANK.get(level, 99), -float(item.get("relevance_score") or 0))

    @staticmethod
    def _row_fields(
        item: Union[RankedArtefact, dict[str, Any]],
    ) -> tuple[str, str, str, float, str]:
        """Normalise a ranked artefact or dict into table cell values."""
        if isinstance(item, RankedArtefact):
            summary = (
                item.classification_reasoning
                or item.source_path
                or item.artefact_id
            )
            return (
                item.artefact_id,
                item.category.value,
                item.suspicion_level.value,
                float(item.relevance_score),
                str(summary),
            )
        summary = (
            item.get("classification_reasoning")
            or item.get("source_path")
            or item.get("artefact_id")
            or ""
        )
        return (
            str(item.get("artefact_id") or ""),
            str(item.get("category") or ""),
            str(item.get("suspicion_level") or "informational").lower(),
            float(item.get("relevance_score") or 0.0),
            str(summary),
        )

    @staticmethod
    def _executive_summary(narrative: str) -> str:
        """Extract executive summary text from the narrative body."""
        block = HTMLReportExporter._section(narrative, "Executive Summary")
        if block:
            return block
        return narrative.strip()[:2000] or "No executive summary available."

    @staticmethod
    def _disclaimer(narrative: str, report: ForensicReport) -> str:
        """Extract or synthesise the LLM disclaimer."""
        block = HTMLReportExporter._section(narrative, "LLM Disclaimer")
        if block:
            return block
        model = report.narrative_report.llm_model_used or "unknown"
        return (
            f"DISCLAIMER: This investigative narrative was generated by {model}. "
            "AI-generated content must be verified against the structured JSON "
            "artefact data, which serves as the primary evidential record. "
            "LLM outputs may contain inaccuracies (Scanlon et al., 2023)."
        )

    @staticmethod
    def _iocs(report: ForensicReport, narrative: str) -> list[str]:
        """Collect IOC strings from params or narrative."""
        from_params = report.narrative_report.generation_parameters.get("iocs_identified")
        if isinstance(from_params, list) and from_params:
            return [str(item) for item in from_params]
        block = HTMLReportExporter._section(narrative, "Indicators of Compromise")
        if not block:
            return []
        items: list[str] = []
        for line in block.splitlines():
            cleaned = line.strip().lstrip("-*| ")
            if cleaned and not cleaned.lower().startswith("indicator"):
                items.append(cleaned)
        return items

    @staticmethod
    def _timeline_items(narrative: str, report: ForensicReport) -> list[str]:
        """Collect timeline lines from narrative or artefact timestamps."""
        block = HTMLReportExporter._section(narrative, "Timeline of Events")
        if not block:
            block = HTMLReportExporter._section(narrative, "Timeline")
        if block:
            return [line.strip("- ").strip() for line in block.splitlines() if line.strip()]
        events: list[str] = []
        for row in report.json_report.artefact_data or []:
            if not isinstance(row, dict):
                continue
            raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            stamp = (
                raw.get("timestamp")
                or raw.get("create_time")
                or raw.get("last_visit_time")
                or raw.get("modified_time")
            )
            if stamp is None:
                continue
            events.append(
                f"{stamp} | {row.get('category')} | "
                f"{row.get('source_path') or row.get('artefact_id')}"
            )
        return events

    @staticmethod
    def _section(narrative: str, heading: str) -> Optional[str]:
        """Return the body under a markdown ``##`` heading, if present."""
        if not narrative:
            return None
        pattern = re.compile(
            rf"^##\s+{re.escape(heading)}\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        match = pattern.search(narrative)
        if not match:
            return None
        rest = narrative[match.end() :]
        next_heading = re.search(r"^##\s+", rest, re.MULTILINE)
        block = rest[: next_heading.start()] if next_heading else rest
        return block.strip() or None
