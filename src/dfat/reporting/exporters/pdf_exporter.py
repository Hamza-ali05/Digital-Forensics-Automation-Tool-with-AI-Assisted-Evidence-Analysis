"""PDF forensic report exporter with plaintext graceful degradation.

Generates offline-distributable evidence packages from ``ForensicReport``
data. Prefers ReportLab, then WeasyPrint when available; otherwise writes a
structured ``.txt`` fallback with the same section outline.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from dfat import __version__
from dfat.core.enums import SuspicionLevel
from dfat.core.models.report import ForensicReport

logger = logging.getLogger(__name__)

_SUSPICION_ORDER: dict[str, int] = {
    SuspicionLevel.CRITICAL.value: 0,
    SuspicionLevel.HIGH.value: 1,
    SuspicionLevel.MEDIUM.value: 2,
    SuspicionLevel.LOW.value: 3,
    SuspicionLevel.INFORMATIONAL.value: 4,
}

_SUSPICION_COLOURS: dict[str, str] = {
    SuspicionLevel.CRITICAL.value: "#B71C1C",
    SuspicionLevel.HIGH.value: "#E65100",
    SuspicionLevel.MEDIUM.value: "#F9A825",
    SuspicionLevel.LOW.value: "#1565C0",
    SuspicionLevel.INFORMATIONAL.value: "#546E7A",
}

_SECTION_HEADINGS = (
    "Cover Page",
    "Table of Contents",
    "Executive Summary",
    "Key Findings",
    "Artefact Summary",
    "Timeline",
    "Indicators of Compromise",
    "Statistics",
    "Audit Trail Summary",
    "LLM Disclaimer",
    "JSON Data Appendix",
)


def _reportlab_available() -> bool:
    """Return True when reportlab can be imported."""
    try:
        import reportlab  # noqa: F401

        return True
    except ImportError:
        return False


def _weasyprint_available() -> bool:
    """Return True when weasyprint imports and loads native libs."""
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:  # noqa: BLE001 — missing native deps are common
        return False


class PDFReportExporter:
    """Export a ``ForensicReport`` to PDF (or plaintext fallback)."""

    def __init__(self, output_dir: Path) -> None:
        """Initialise the exporter.

        Args:
            output_dir: Directory where exported files are written.
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        report: ForensicReport,
        include_narrative: bool = True,
        include_json_appendix: bool = True,
    ) -> Path:
        """Generate a PDF (or plaintext fallback) for ``report``.

        Args:
            report: Combined dual-output forensic report.
            include_narrative: Include narrative-derived sections.
            include_json_appendix: Append truncated JSON artefact data.

        Returns:
            Path to the generated ``.pdf`` or ``.txt`` file.
        """
        if _reportlab_available():
            try:
                return self._generate_reportlab_pdf(
                    report,
                    include_narrative=include_narrative,
                    include_json_appendix=include_json_appendix,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "ReportLab PDF generation failed; trying WeasyPrint/fallback"
                )

        if _weasyprint_available():
            try:
                return self._generate_weasyprint_pdf(
                    report,
                    include_narrative=include_narrative,
                    include_json_appendix=include_json_appendix,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "WeasyPrint PDF generation failed; using plaintext fallback"
                )

        logger.warning(
            "Neither reportlab nor weasyprint available/usable; "
            "writing plaintext fallback for report %s",
            report.report_id,
        )
        return self._generate_plaintext_fallback(
            report,
            include_narrative=include_narrative,
            include_json_appendix=include_json_appendix,
        )

    def _output_path(self, report: ForensicReport, suffix: str) -> Path:
        """Build a deterministic output path for the report export."""
        safe_case = re.sub(r"[^\w\-]+", "_", report.case.case_name).strip("_") or "case"
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"dfat_report_{safe_case}_{report.report_id[:8]}_{stamp}{suffix}"
        return self._output_dir / filename

    def _generate_reportlab_pdf(
        self,
        report: ForensicReport,
        *,
        include_narrative: bool,
        include_json_appendix: bool,
    ) -> Path:
        """Render the report with ReportLab Platypus."""
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        path = self._output_path(report, ".pdf")
        sections = self._build_section_content(
            report,
            include_narrative=include_narrative,
            include_json_appendix=include_json_appendix,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DFATTitle",
            parent=styles["Title"],
            fontSize=22,
            spaceAfter=18,
            alignment=TA_CENTER,
        )
        heading_style = ParagraphStyle(
            "DFATHeading",
            parent=styles["Heading1"],
            fontSize=14,
            spaceBefore=12,
            spaceAfter=8,
            textColor=colors.HexColor("#1A237E"),
        )
        body_style = ParagraphStyle(
            "DFATBody",
            parent=styles["BodyText"],
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        )
        mono_style = ParagraphStyle(
            "DFATMono",
            parent=styles["Code"],
            fontSize=8,
            leading=10,
            fontName="Courier",
        )

        story: list[Any] = []

        # 1. Cover page
        cover = sections["cover"]
        story.append(Spacer(1, 1.5 * inch))
        story.append(Paragraph("DFAT Forensic Report", title_style))
        story.append(Spacer(1, 0.4 * inch))
        for line in cover:
            story.append(Paragraph(self._escape(line), body_style))
        story.append(PageBreak())

        # 2. Table of contents
        story.append(Paragraph("Table of Contents", heading_style))
        for index, heading in enumerate(_SECTION_HEADINGS, start=1):
            if heading == "JSON Data Appendix" and not include_json_appendix:
                continue
            if heading in {"Executive Summary", "Key Findings", "Timeline"} and not include_narrative:
                continue
            story.append(Paragraph(f"{index}. {heading}", body_style))
        story.append(PageBreak())

        # 3–10. Content sections
        ordered = [
            ("Executive Summary", "executive_summary"),
            ("Key Findings", "key_findings"),
            ("Artefact Summary", "artefact_summary"),
            ("Timeline", "timeline"),
            ("Indicators of Compromise", "iocs"),
            ("Statistics", "statistics"),
            ("Audit Trail Summary", "audit"),
            ("LLM Disclaimer", "disclaimer"),
        ]
        for title, key in ordered:
            if key in {"executive_summary", "key_findings", "timeline"} and not include_narrative:
                continue
            story.append(Paragraph(title, heading_style))
            content = sections.get(key, [])
            if key == "artefact_summary" and sections.get("artefact_table"):
                table = Table(sections["artefact_table"], repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A237E")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                        ]
                    )
                )
                # Colour-code suspicion column (index 2).
                for row_idx, row in enumerate(sections["artefact_table"][1:], start=1):
                    level = str(row[2]).lower()
                    hex_colour = _SUSPICION_COLOURS.get(level)
                    if hex_colour:
                        table.setStyle(
                            TableStyle(
                                [
                                    (
                                        "TEXTCOLOR",
                                        (2, row_idx),
                                        (2, row_idx),
                                        colors.HexColor(hex_colour),
                                    ),
                                    (
                                        "FONTNAME",
                                        (2, row_idx),
                                        (2, row_idx),
                                        "Helvetica-Bold",
                                    ),
                                ]
                            )
                        )
                story.append(table)
                story.append(Spacer(1, 0.2 * inch))
            elif key == "statistics" and sections.get("stats_tables"):
                for caption, rows in sections["stats_tables"]:
                    story.append(Paragraph(self._escape(caption), body_style))
                    stats_table = Table(rows, repeatRows=1)
                    stats_table.setStyle(
                        TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474F")),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                                ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ]
                        )
                    )
                    story.append(stats_table)
                    story.append(Spacer(1, 0.15 * inch))
            else:
                for line in content:
                    style = mono_style if key == "disclaimer" and line.startswith("DISCLAIMER") else body_style
                    story.append(Paragraph(self._escape(line).replace("\n", "<br/>"), style))
            story.append(PageBreak())

        # 11. JSON appendix
        if include_json_appendix:
            story.append(Paragraph("JSON Data Appendix", heading_style))
            for line in sections.get("json_appendix_notes", []):
                story.append(Paragraph(self._escape(line), body_style))
            story.append(Paragraph(self._escape(sections.get("json_appendix", "")), mono_style))

        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            title=f"DFAT Report — {report.case.case_name}",
            author=report.case.investigator,
        )
        doc.build(story)
        return path

    def _generate_weasyprint_pdf(
        self,
        report: ForensicReport,
        *,
        include_narrative: bool,
        include_json_appendix: bool,
    ) -> Path:
        """Render the report via WeasyPrint HTML."""
        from weasyprint import HTML

        path = self._output_path(report, ".pdf")
        html = self._build_html(
            report,
            include_narrative=include_narrative,
            include_json_appendix=include_json_appendix,
        )
        HTML(string=html).write_pdf(str(path))
        return path

    def _generate_plaintext_fallback(
        self,
        report: ForensicReport,
        include_narrative: bool = True,
        include_json_appendix: bool = True,
    ) -> Path:
        """Write a well-formatted plaintext report with the same sections.

        Args:
            report: Combined dual-output forensic report.
            include_narrative: Include narrative-derived sections.
            include_json_appendix: Append truncated JSON artefact data.

        Returns:
            Path to the generated ``.txt`` file.
        """
        path = self._output_path(report, ".txt")
        sections = self._build_section_content(
            report,
            include_narrative=include_narrative,
            include_json_appendix=include_json_appendix,
        )
        lines: list[str] = []
        lines.append("=" * 72)
        lines.append("DFAT FORENSIC REPORT (PLAINTEXT FALLBACK)")
        lines.append("=" * 72)
        lines.append("")
        lines.append("## Cover Page")
        lines.extend(sections["cover"])
        lines.append("")
        lines.append("## Table of Contents")
        for index, heading in enumerate(_SECTION_HEADINGS, start=1):
            lines.append(f"  {index}. {heading}")
        lines.append("")

        def _block(title: str, body: list[str]) -> None:
            lines.append(f"## {title}")
            lines.extend(body if body else ["(none)"])
            lines.append("")

        if include_narrative:
            _block("Executive Summary", sections["executive_summary"])
            _block("Key Findings", sections["key_findings"])
        _block("Artefact Summary (top 50)", sections["artefact_summary"])
        if include_narrative:
            _block("Timeline", sections["timeline"])
        _block("Indicators of Compromise", sections["iocs"])
        _block("Statistics", sections["statistics"])
        _block("Audit Trail Summary", sections["audit"])
        _block("LLM Disclaimer", sections["disclaimer"])
        if include_json_appendix:
            _block("JSON Data Appendix", sections.get("json_appendix_notes", []))
            lines.append(sections.get("json_appendix", ""))
            lines.append("")

        lines.append("=" * 72)
        lines.append(
            "Structured JSON remains the primary evidential record "
            "(Scanlon et al., 2023)."
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _build_section_content(
        self,
        report: ForensicReport,
        *,
        include_narrative: bool,
        include_json_appendix: bool,
    ) -> dict[str, Any]:
        """Assemble plain-text / table payloads for each PDF section."""
        narrative = report.narrative_report.summary_text if include_narrative else ""
        artefacts = list(report.json_report.artefact_data or [])
        top_artefacts = self._top_artefacts(artefacts, limit=50)

        cover = [
            f"Case name: {report.case.case_name}",
            f"Case ID: {report.case.case_id}",
            f"Evidence ID: {report.json_report.evidence_id}",
            f"Report ID: {report.report_id}",
            f"Investigator: {report.case.investigator}",
            f"Generated at (UTC): {report.json_report.generated_at.isoformat()}",
            f"DFAT version: {__version__}",
            f"Integrity hash: {report.json_report.integrity_hash}",
            f"Schema version: {report.json_report.schema_version}",
        ]

        executive = self._extract_narrative_section(narrative, "Executive Summary")
        if not executive:
            executive = [narrative.strip()[:2000] or "No executive summary available."]

        key_findings = self._extract_narrative_section(narrative, "Key Findings")
        if not key_findings:
            key_findings = self._findings_from_artefacts(top_artefacts)

        timeline = self._extract_narrative_section(narrative, "Timeline of Events")
        if not timeline:
            timeline = self._extract_narrative_section(narrative, "Timeline")
        if not timeline:
            timeline = self._timeline_from_artefacts(artefacts)

        iocs = self._extract_narrative_section(narrative, "Indicators of Compromise")
        if not iocs:
            iocs = list(
                report.narrative_report.generation_parameters.get("iocs_identified") or []
            )
            if not iocs:
                iocs = ["No indicators of compromise recorded."]

        stats_lines, stats_tables = self._statistics_blocks(artefacts)
        audit_lines = self._audit_lines(report)
        disclaimer = self._disclaimer_lines(report, narrative)

        artefact_summary = [
            f"{row.get('artefact_id', '?')} | "
            f"{row.get('category', '?')} | "
            f"{row.get('suspicion_level', '?')} | "
            f"score={row.get('relevance_score', 0)}"
            for row in top_artefacts
        ] or ["No artefacts available."]

        artefact_table: list[list[str]] = [
            ["Artefact ID", "Category", "Suspicion", "Score", "Source"]
        ]
        for row in top_artefacts:
            artefact_table.append(
                [
                    str(row.get("artefact_id", ""))[:24],
                    str(row.get("category", "")),
                    str(row.get("suspicion_level", "")),
                    f"{float(row.get('relevance_score') or 0):.2f}",
                    str(row.get("source_path") or "")[:40],
                ]
            )

        json_notes: list[str] = []
        json_appendix = ""
        if include_json_appendix:
            truncated = artefacts
            if len(artefacts) > 100:
                truncated = artefacts[:100]
                json_notes.append(
                    f"Appendix truncated to first 100 of {len(artefacts)} artefacts."
                )
            else:
                json_notes.append(f"Appendix includes all {len(artefacts)} artefacts.")
            json_appendix = json.dumps(
                {
                    "report_id": report.report_id,
                    "evidence_id": report.json_report.evidence_id,
                    "integrity_hash": report.json_report.integrity_hash,
                    "artefacts": truncated,
                },
                indent=2,
                default=str,
            )

        return {
            "cover": cover,
            "executive_summary": executive,
            "key_findings": key_findings,
            "artefact_summary": artefact_summary,
            "artefact_table": artefact_table,
            "timeline": timeline,
            "iocs": iocs if isinstance(iocs, list) else [str(iocs)],
            "statistics": stats_lines,
            "stats_tables": stats_tables,
            "audit": audit_lines,
            "disclaimer": disclaimer,
            "json_appendix_notes": json_notes,
            "json_appendix": json_appendix,
        }

    @staticmethod
    def _top_artefacts(artefacts: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
        """Return artefacts sorted by suspicion then relevance score."""

        def _sort_key(row: dict[str, Any]) -> tuple[int, float]:
            level = str(row.get("suspicion_level") or "").lower()
            score = float(row.get("relevance_score") or 0.0)
            return (_SUSPICION_ORDER.get(level, 99), -score)

        return sorted(artefacts, key=_sort_key)[:limit]

    @staticmethod
    def _extract_narrative_section(narrative: str, heading: str) -> list[str]:
        """Extract lines under a markdown ``## Heading`` block."""
        if not narrative:
            return []
        pattern = re.compile(
            rf"^##\s+{re.escape(heading)}\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        match = pattern.search(narrative)
        if not match:
            return []
        rest = narrative[match.end() :]
        next_heading = re.search(r"^##\s+", rest, re.MULTILINE)
        block = rest[: next_heading.start()] if next_heading else rest
        lines = [line.rstrip() for line in block.strip().splitlines() if line.strip()]
        return lines

    @staticmethod
    def _findings_from_artefacts(artefacts: list[dict[str, Any]]) -> list[str]:
        """Build key-finding bullets from top artefacts."""
        findings: list[str] = []
        for row in artefacts[:20]:
            reasoning = row.get("classification_reasoning") or ""
            findings.append(
                f"- [{row.get('suspicion_level')}] {row.get('category')}: "
                f"{row.get('source_path') or row.get('artefact_id')} "
                f"{('— ' + reasoning) if reasoning else ''}".rstrip()
            )
        return findings or ["No key findings available."]

    @staticmethod
    def _timeline_from_artefacts(artefacts: list[dict[str, Any]]) -> list[str]:
        """Best-effort timeline lines from artefact raw_data timestamps."""
        events: list[str] = []
        for row in artefacts:
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
        return events or ["Insufficient temporal data for a timeline."]

    @staticmethod
    def _statistics_blocks(
        artefacts: list[dict[str, Any]],
    ) -> tuple[list[str], list[tuple[str, list[list[str]]]]]:
        """Build statistics text lines and table rows."""
        by_category: dict[str, int] = {}
        by_level: dict[str, int] = {}
        for row in artefacts:
            cat = str(row.get("category") or "unknown")
            level = str(row.get("suspicion_level") or "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
            by_level[level] = by_level.get(level, 0) + 1

        lines = [f"Total artefacts: {len(artefacts)}", "", "By category:"]
        for key, count in sorted(by_category.items()):
            lines.append(f"  - {key}: {count}")
        lines.append("")
        lines.append("By suspicion level:")
        for key, count in sorted(by_level.items()):
            lines.append(f"  - {key}: {count}")

        cat_table = [["Category", "Count"]] + [
            [k, str(v)] for k, v in sorted(by_category.items())
        ]
        level_table = [["Suspicion level", "Count"]] + [
            [k, str(v)] for k, v in sorted(by_level.items())
        ]
        tables = [
            ("Counts by category", cat_table),
            ("Counts by suspicion level", level_table),
        ]
        return lines, tables

    @staticmethod
    def _audit_lines(report: ForensicReport) -> list[str]:
        """Format audit metadata and stage timings."""
        lines: list[str] = []
        audit = report.audit_metadata or {}
        if audit:
            for key, value in sorted(audit.items()):
                lines.append(f"{key}: {value}")
        else:
            lines.append("No audit_metadata embedded on this report.")
        lines.append("")
        lines.append(f"Pipeline duration (s): {report.pipeline_duration_seconds:.3f}")
        if report.stage_timings:
            lines.append("Stage timings:")
            for stage, seconds in sorted(report.stage_timings.items()):
                lines.append(f"  - {stage}: {float(seconds):.3f}s")
        return lines

    @staticmethod
    def _disclaimer_lines(report: ForensicReport, narrative: str) -> list[str]:
        """Prefer narrative disclaimer; else emit the standard Scanlon text."""
        extracted = PDFReportExporter._extract_narrative_section(narrative, "LLM Disclaimer")
        if extracted:
            return extracted
        model = report.narrative_report.llm_model_used or "unknown"
        return [
            f"DISCLAIMER: This investigative narrative was generated by {model}. "
            "AI-generated content must be verified against the structured JSON "
            "artefact data, which serves as the primary evidential record. "
            "LLM outputs may contain inaccuracies (Scanlon et al., 2023). "
            "This summary is for investigative guidance only and does not "
            "constitute expert testimony.",
        ]

    def _build_html(
        self,
        report: ForensicReport,
        *,
        include_narrative: bool,
        include_json_appendix: bool,
    ) -> str:
        """Build a simple HTML document for WeasyPrint rendering."""
        sections = self._build_section_content(
            report,
            include_narrative=include_narrative,
            include_json_appendix=include_json_appendix,
        )

        def _pre(lines: list[str]) -> str:
            return "<pre>" + self._escape("\n".join(lines)) + "</pre>"

        parts = [
            "<html><head><meta charset='utf-8'><title>DFAT Forensic Report</title>",
            "<style>body{font-family:sans-serif;margin:2cm} h1,h2{color:#1A237E} "
            "pre{white-space:pre-wrap;font-size:10pt}</style></head><body>",
            "<h1>DFAT Forensic Report</h1>",
            "<h2>Cover Page</h2>",
            _pre(sections["cover"]),
            "<h2>Table of Contents</h2><ol>",
        ]
        for heading in _SECTION_HEADINGS:
            parts.append(f"<li>{self._escape(heading)}</li>")
        parts.append("</ol>")
        if include_narrative:
            parts.append("<h2>Executive Summary</h2>")
            parts.append(_pre(sections["executive_summary"]))
            parts.append("<h2>Key Findings</h2>")
            parts.append(_pre(sections["key_findings"]))
        parts.append("<h2>Artefact Summary</h2>")
        parts.append(_pre(sections["artefact_summary"]))
        if include_narrative:
            parts.append("<h2>Timeline</h2>")
            parts.append(_pre(sections["timeline"]))
        parts.append("<h2>Indicators of Compromise</h2>")
        parts.append(_pre(sections["iocs"]))
        parts.append("<h2>Statistics</h2>")
        parts.append(_pre(sections["statistics"]))
        parts.append("<h2>Audit Trail Summary</h2>")
        parts.append(_pre(sections["audit"]))
        parts.append("<h2>LLM Disclaimer</h2>")
        parts.append(_pre(sections["disclaimer"]))
        if include_json_appendix:
            parts.append("<h2>JSON Data Appendix</h2>")
            parts.append(_pre(sections.get("json_appendix_notes", [])))
            parts.append(f"<pre>{self._escape(sections.get('json_appendix', ''))}</pre>")
        parts.append("</body></html>")
        return "\n".join(parts)

    @staticmethod
    def _escape(text: str) -> str:
        """Escape text for ReportLab/HTML paragraph content."""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
