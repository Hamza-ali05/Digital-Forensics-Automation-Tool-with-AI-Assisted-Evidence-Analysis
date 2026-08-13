"""Formal chain-of-custody report generation for evidence packages."""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional, Union

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict, Field

from dfat.core.models.case import Case
from dfat.evidence_management.custody_service import ChainOfCustodyService
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.models import ChainOfCustodyRecord, HashSet


class CustodyReport(BaseModel):
    """Formal chain-of-custody report for court / evidence-package use."""

    model_config = ConfigDict(frozen=False)

    evidence_id: str
    case_name: str
    evidence_file_path: str
    hash_set: HashSet
    chain: list[ChainOfCustodyRecord] = Field(default_factory=list)
    chain_length: int = 0
    verification: dict[str, Any] = Field(default_factory=dict)
    first_acquired: datetime
    last_action: datetime
    integrity_verified: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CustodyReportGenerator:
    """Build and export formal chain-of-custody reports."""

    def __init__(
        self,
        custody_service: ChainOfCustodyService,
        hash_service: MultiHashService,
        template_dir: Path,
    ) -> None:
        """Initialise the generator.

        Args:
            custody_service: Chain-of-custody service.
            hash_service: Multi-algorithm evidence hash service.
            template_dir: Directory containing ``custody_report.j2``.
        """
        self._custody_service = custody_service
        self._hash_service = hash_service
        self._template_dir = Path(template_dir)
        self._env = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=select_autoescape(enabled_extensions=()),
        )

    async def generate(
        self,
        evidence_id: str,
        case: Case,
        *,
        evidence_file_path: Optional[Union[Path, str]] = None,
    ) -> CustodyReport:
        """Generate a formal custody report for an evidence item.

        Args:
            evidence_id: Evidence identifier.
            case: Full case model providing the case name.
            evidence_file_path: Optional explicit path; when omitted, resolved
                via ``ChainOfCustodyService.generate_custody_report``.

        Returns:
            Populated ``CustodyReport`` including verification and hash set.
        """
        chain = await self._custody_service.get_custody_chain(evidence_id)
        file_path = await self._resolve_file_path(evidence_id, evidence_file_path)

        verification = await self._custody_service.verify_custody_chain(
            evidence_id,
            file_path,
        )
        hash_set = self._hash_service.compute_hash_set(Path(file_path), evidence_id)

        now = datetime.now(UTC)
        if chain:
            first_acquired = chain[0].timestamp
            last_action = chain[-1].timestamp
        else:
            first_acquired = now
            last_action = now

        return CustodyReport(
            evidence_id=evidence_id,
            case_name=case.case_name,
            evidence_file_path=str(file_path),
            hash_set=hash_set,
            chain=list(chain),
            chain_length=len(chain),
            verification=dict(verification),
            first_acquired=first_acquired,
            last_action=last_action,
            integrity_verified=bool(verification.get("integrity_verified")),
            generated_at=now,
        )

    async def export_text(self, report: CustodyReport) -> str:
        """Render ``custody_report.j2`` into formatted plain text.

        Args:
            report: Custody report to render.

        Returns:
            Formatted text suitable for evidence packages.
        """
        template = self._env.get_template("custody_report.j2")
        return template.render(
            report=report,
            case_name=report.case_name,
            evidence_id=report.evidence_id,
            evidence_file_path=report.evidence_file_path,
            hash_set=report.hash_set,
            chain=report.chain,
            chain_length=report.chain_length,
            verification=report.verification,
            first_acquired=report.first_acquired.isoformat(),
            last_action=report.last_action.isoformat(),
            integrity_verified=report.integrity_verified,
            generated_at=report.generated_at.isoformat(),
            issues=list(report.verification.get("issues") or []),
        )

    async def export_html(self, report: CustodyReport) -> str:
        """Render the custody chain as an HTML table with key metadata.

        Args:
            report: Custody report to render.

        Returns:
            Self-contained HTML fragment/document string.
        """
        rows: list[str] = []
        for record in report.chain:
            action = getattr(record.action, "value", record.action)
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(record.entry_number or ''))}</td>"
                f"<td>{html.escape(record.timestamp.isoformat())}</td>"
                f"<td>{html.escape(str(action))}</td>"
                f"<td>{html.escape(record.performed_by_name)} "
                f"({html.escape(record.performed_by_user_id)})</td>"
                f"<td>{html.escape(record.reason)}</td>"
                f"<td><code>{html.escape(record.hash_at_action)}</code></td>"
                f"<td>{html.escape(record.location)}</td>"
                f"<td>{html.escape(record.notes or '')}</td>"
                "</tr>"
            )
        if not rows:
            rows.append('<tr><td colspan="8">No custody entries recorded.</td></tr>')

        issues = report.verification.get("issues") or []
        issue_items = "".join(f"<li>{html.escape(str(item))}</li>" for item in issues)
        issues_block = (
            f"<ul>{issue_items}</ul>" if issues else "<p>No verification issues.</p>"
        )
        status = "VERIFIED" if report.integrity_verified else "FAILED / UNVERIFIED"

        return (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
            f"<title>Chain of Custody — {html.escape(report.case_name)}</title>"
            "<style>"
            "body{font-family:Segoe UI,Arial,sans-serif;margin:1.5rem;color:#1b2430}"
            "h1,h2{color:#1a237e} table{border-collapse:collapse;width:100%;font-size:0.9rem}"
            "th,td{border:1px solid #d7dde5;padding:0.4rem 0.55rem;text-align:left;vertical-align:top}"
            "th{background:#eceff7} code{font-size:0.78rem}"
            ".ok{color:#1b5e20;font-weight:700}.bad{color:#b71c1c;font-weight:700}"
            "dl{display:grid;grid-template-columns:14rem 1fr;gap:0.35rem 1rem}"
            "dt{color:#5c6b7a;font-size:0.8rem;text-transform:uppercase}"
            "dd{margin:0;font-weight:600;word-break:break-all}"
            "</style></head><body>"
            "<h1>Chain of Custody Report</h1>"
            "<dl>"
            f"<dt>Case</dt><dd>{html.escape(report.case_name)}</dd>"
            f"<dt>Evidence ID</dt><dd>{html.escape(report.evidence_id)}</dd>"
            f"<dt>File path</dt><dd>{html.escape(report.evidence_file_path)}</dd>"
            f"<dt>MD5</dt><dd><code>{html.escape(report.hash_set.md5)}</code></dd>"
            f"<dt>SHA-1</dt><dd><code>{html.escape(report.hash_set.sha1)}</code></dd>"
            f"<dt>SHA-256</dt><dd><code>{html.escape(report.hash_set.sha256)}</code></dd>"
            f"<dt>First acquired</dt><dd>{html.escape(report.first_acquired.isoformat())}</dd>"
            f"<dt>Last action</dt><dd>{html.escape(report.last_action.isoformat())}</dd>"
            f"<dt>Chain length</dt><dd>{report.chain_length}</dd>"
            f"<dt>Integrity</dt><dd class="
            f"{'ok' if report.integrity_verified else 'bad'}>{status}</dd>"
            f"<dt>Generated at</dt><dd>{html.escape(report.generated_at.isoformat())}</dd>"
            "</dl>"
            "<h2>Verification</h2>"
            f"<p>is_valid={html.escape(str(report.verification.get('is_valid')))} · "
            f"total_entries={html.escape(str(report.verification.get('total_entries')))}</p>"
            f"{issues_block}"
            "<h2>Custody Chain</h2>"
            "<table><thead><tr>"
            "<th>#</th><th>Timestamp</th><th>Action</th><th>Actor</th>"
            "<th>Reason</th><th>Hash at action</th><th>Location</th><th>Notes</th>"
            "</tr></thead><tbody>"
            f"{''.join(rows)}"
            "</tbody></table>"
            "<p><em>This custody record is intended for evidence-package and court "
            "documentation. Structured JSON remains the primary evidential artefact "
            "layer (Scanlon et al., 2023).</em></p>"
            "</body></html>"
        )

    async def _resolve_file_path(
        self,
        evidence_id: str,
        evidence_file_path: Optional[Union[Path, str]],
    ) -> Path:
        """Resolve the evidence file path for hashing and verification."""
        if evidence_file_path is not None:
            return Path(evidence_file_path)
        summary = await self._custody_service.generate_custody_report(evidence_id)
        raw = summary.get("evidence_file_path")
        if not raw:
            raise FileNotFoundError(
                f"Could not resolve evidence file path for {evidence_id}"
            )
        return Path(str(raw))
