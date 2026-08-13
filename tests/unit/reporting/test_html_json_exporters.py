"""Unit tests for HTML and JSON file exporters (Prompt 6.7)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from dfat.core.enums import HashAlgorithm
from dfat.core.exceptions import IntegrityVerificationError
from dfat.core.models.case import Case
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.reporting.exporters.html_exporter import HTMLReportExporter
from dfat.reporting.exporters.json_file_exporter import JSONFileExporter
from dfat.shared.hashing import compute_data_hash


def _template_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "src"
        / "dfat"
        / "reporting"
        / "templates"
    )


def _hash_artefacts(artefacts: list[dict]) -> str:
    canonical = json.dumps(
        artefacts,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return compute_data_hash(canonical.encode("utf-8"), HashAlgorithm.SHA256)


def _artefacts() -> list[dict]:
    return [
        {
            "artefact_id": "art-crit",
            "category": "injected_code",
            "suspicion_level": "critical",
            "relevance_score": 0.99,
            "source_path": "/mem/rwx",
            "raw_data": {"timestamp": "2024-01-01T00:00:00Z"},
            "classification_reasoning": "RWX region",
        },
        {
            "artefact_id": "art-high",
            "category": "registry_key",
            "suspicion_level": "high",
            "relevance_score": 0.8,
            "source_path": "HKCU\\Run",
            "raw_data": {},
            "classification_reasoning": "Persistence",
        },
        {
            "artefact_id": "art-low",
            "category": "browser_history",
            "suspicion_level": "low",
            "relevance_score": 0.2,
            "source_path": "history.db",
            "raw_data": {},
            "classification_reasoning": "Benign browse",
        },
    ]


def _case() -> Case:
    return Case(
        metadata=CaseMetadata(
            case_name="HTML Export Case",
            investigator="Lead Analyst",
        ),
        evidence_ids=["ev-html-1"],
        tags=["malware", "lab"],
        lead_investigator_id="user-lead",
    )


def _report(artefacts: list[dict] | None = None) -> ForensicReport:
    rows = artefacts if artefacts is not None else _artefacts()
    return ForensicReport(
        case=_case().metadata,
        json_report=JSONReport(
            report_id=str(uuid4()),
            evidence_id="ev-html-1",
            artefact_data=rows,
            integrity_hash=_hash_artefacts(rows),
            generated_at=datetime.now(UTC),
        ),
        narrative_report=NarrativeReport(
            evidence_id="ev-html-1",
            summary_text=(
                "## LLM Disclaimer\n\n"
                "DISCLAIMER: test (Scanlon et al., 2023).\n\n"
                "## Executive Summary\n\n"
                "Injected code and persistence observed.\n\n"
                "## Indicators of Compromise\n\n"
                "- evil.exe\n"
            ),
            llm_model_used="test-model",
            generation_parameters={"iocs_identified": ["evil.exe"]},
        ),
        pipeline_duration_seconds=3.0,
        audit_metadata={
            "generated_by_user_id": "user-lead",
            "pipeline_job_id": "job-42",
            "custody_chain_entries": 2,
            "generation_host": "lab-host",
        },
    )


def test_html_export_is_self_contained(tmp_path: Path) -> None:
    """Verify HTML has inline CSS/JS and no external stylesheet/script URLs."""
    exporter = HTMLReportExporter(tmp_path, _template_dir())
    path = exporter.export(_report(), _case())
    assert path.suffix == ".html"
    assert path.parent == tmp_path
    text = path.read_text(encoding="utf-8")
    assert "<style>" in text
    assert "<script>" in text
    assert 'href="http' not in text.lower()
    assert "cdn." not in text.lower()
    assert re.search(r'<link[^>]+rel=["\']stylesheet', text, re.I) is None
    assert re.search(r'<script[^>]+src=', text, re.I) is None
    for section in (
        "Case Information",
        "Executive Summary",
        "Findings",
        "Timeline",
        "Indicators of Compromise",
        "Statistics",
        "Chain-of-Custody Summary",
        "LLM Disclaimer",
        "JSON Data Viewer",
    ):
        assert section in text


def test_html_artefact_table_colour_coding(tmp_path: Path) -> None:
    """Verify findings table rows use suspicion colour CSS classes."""
    exporter = HTMLReportExporter(tmp_path, _template_dir())
    text = exporter.export(_report(), _case()).read_text(encoding="utf-8")
    assert 'class="row-critical"' in text
    assert 'class="row-high"' in text
    assert 'class="row-low"' in text
    assert 'badge-critical' in text
    assert "art-crit" in text


def test_json_file_matches_memory_and_verifies(tmp_path: Path) -> None:
    """Verify JSON file matches in-memory data and integrity hash verifies."""
    report = _report()
    exporter = JSONFileExporter()
    path = exporter.export(report.json_report, tmp_path)
    assert path.suffix == ".json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["report_id"] == report.json_report.report_id
    assert loaded["evidence_id"] == report.json_report.evidence_id
    assert loaded["integrity_hash"] == report.json_report.integrity_hash
    assert loaded["artefacts"] == report.json_report.artefact_data


def test_json_export_raw_rejects_tampered_hash(tmp_path: Path) -> None:
    """Verify export_raw raises when integrity_hash does not match artefacts."""
    artefacts = _artefacts()
    document = {
        "schema_version": "1.0.0",
        "report_id": str(uuid4()),
        "evidence_id": "ev-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "integrity_hash": "0" * 64,
        "artefacts": artefacts,
    }
    exporter = JSONFileExporter()
    with pytest.raises(IntegrityVerificationError):
        exporter.export_raw(document, tmp_path / "bad.json")
