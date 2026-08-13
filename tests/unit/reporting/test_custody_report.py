"""Unit tests for chain-of-custody report generation (Prompt 6.8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dfat.case_management.enums import CustodyAction
from dfat.core.models.case import Case
from dfat.core.models.evidence import CaseMetadata
from dfat.evidence_management.models import ChainOfCustodyRecord, HashSet
from dfat.reporting.generators.custody_report import (
    CustodyReport,
    CustodyReportGenerator,
)


def _template_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "src"
        / "dfat"
        / "reporting"
        / "templates"
    )


def _case() -> Case:
    return Case(
        metadata=CaseMetadata(
            case_name="Custody Court Case",
            investigator="Lead Examiner",
        ),
        evidence_ids=["ev-custody-1"],
    )


def _hash_set(path: Path) -> HashSet:
    return HashSet(
        md5="d" * 32,
        sha1="e" * 40,
        sha256="f" * 64,
        file_size_bytes=path.stat().st_size,
        computed_at=datetime.now(UTC),
    )


def _chain(evidence_id: str, digest: str) -> list[ChainOfCustodyRecord]:
    t0 = datetime.now(UTC) - timedelta(hours=2)
    t1 = datetime.now(UTC) - timedelta(hours=1)
    return [
        ChainOfCustodyRecord(
            record_id=str(uuid4()),
            evidence_id=evidence_id,
            action=CustodyAction.ACQUIRED,
            performed_by_user_id="u1",
            performed_by_name="Alice",
            timestamp=t0,
            reason="Initial acquisition",
            hash_at_action=digest,
            entry_number=1,
            notes="Sealed drive",
        ),
        ChainOfCustodyRecord(
            record_id=str(uuid4()),
            evidence_id=evidence_id,
            action=CustodyAction.ANALYSED,
            performed_by_user_id="u2",
            performed_by_name="Bob",
            timestamp=t1,
            reason="Lab analysis",
            hash_at_action=digest,
            entry_number=2,
        ),
    ]


@pytest.mark.asyncio
async def test_generate_includes_chain_verification_and_hash_set(
    tmp_path: Path,
) -> None:
    """Verify custody report includes chain, verification, and all hash algos."""
    evidence_file = tmp_path / "evidence.bin"
    evidence_file.write_bytes(b"custody-evidence-bytes")
    evidence_id = "ev-custody-1"
    digest = "f" * 64
    chain = _chain(evidence_id, digest)
    verification = {
        "is_valid": True,
        "total_entries": 2,
        "integrity_verified": True,
        "issues": [],
    }

    custody_service = MagicMock()
    custody_service.get_custody_chain = AsyncMock(return_value=chain)
    custody_service.verify_custody_chain = AsyncMock(return_value=verification)
    custody_service.generate_custody_report = AsyncMock(
        return_value={"evidence_file_path": str(evidence_file)}
    )

    hash_service = MagicMock()
    hash_service.compute_hash_set = MagicMock(return_value=_hash_set(evidence_file))

    generator = CustodyReportGenerator(
        custody_service=custody_service,
        hash_service=hash_service,
        template_dir=_template_dir(),
    )
    report = await generator.generate(evidence_id, _case())

    assert isinstance(report, CustodyReport)
    assert report.evidence_id == evidence_id
    assert report.case_name == "Custody Court Case"
    assert report.chain_length == 2
    assert len(report.chain) == 2
    assert report.chain[0].action == CustodyAction.ACQUIRED
    assert report.chain[1].performed_by_name == "Bob"
    assert report.verification == verification
    assert report.integrity_verified is True
    assert report.hash_set.md5 == "d" * 32
    assert report.hash_set.sha1 == "e" * 40
    assert report.hash_set.sha256 == "f" * 64
    custody_service.verify_custody_chain.assert_awaited()
    hash_service.compute_hash_set.assert_called_once()


@pytest.mark.asyncio
async def test_export_text_template_renders(tmp_path: Path) -> None:
    """Verify custody_report.j2 renders all required sections."""
    evidence_file = tmp_path / "evidence.bin"
    evidence_file.write_bytes(b"abc")
    evidence_id = "ev-custody-1"
    digest = "f" * 64
    chain = _chain(evidence_id, digest)

    custody_service = MagicMock()
    custody_service.get_custody_chain = AsyncMock(return_value=chain)
    custody_service.verify_custody_chain = AsyncMock(
        return_value={
            "is_valid": True,
            "total_entries": 2,
            "integrity_verified": True,
            "issues": [],
        }
    )
    hash_service = MagicMock()
    hash_service.compute_hash_set = MagicMock(return_value=_hash_set(evidence_file))

    generator = CustodyReportGenerator(
        custody_service=custody_service,
        hash_service=hash_service,
        template_dir=_template_dir(),
    )
    report = await generator.generate(
        evidence_id,
        _case(),
        evidence_file_path=evidence_file,
    )
    text = await generator.export_text(report)

    assert "CHAIN OF CUSTODY REPORT" in text
    assert "Custody Court Case" in text
    assert evidence_id in text
    assert "MD5:" in text and ("d" * 32) in text
    assert "SHA-1:" in text and ("e" * 40) in text
    assert "SHA-256:" in text and ("f" * 64) in text
    assert "Alice" in text and "Bob" in text
    assert "ACQUIRED" in text or "acquired" in text.lower()
    assert "integrity_verified" in text.lower() or "Integrity verified" in text
    assert "Scanlon et al." in text


@pytest.mark.asyncio
async def test_export_html_includes_table_and_actors(tmp_path: Path) -> None:
    """Verify HTML export includes timestamps, actions, and actors."""
    evidence_file = tmp_path / "evidence.bin"
    evidence_file.write_bytes(b"abc")
    evidence_id = "ev-custody-1"
    digest = "a" * 64
    chain = _chain(evidence_id, digest)

    custody_service = MagicMock()
    custody_service.get_custody_chain = AsyncMock(return_value=chain)
    custody_service.verify_custody_chain = AsyncMock(
        return_value={
            "is_valid": True,
            "total_entries": 2,
            "integrity_verified": True,
            "issues": [],
        }
    )
    hash_service = MagicMock()
    hash_service.compute_hash_set = MagicMock(return_value=_hash_set(evidence_file))

    generator = CustodyReportGenerator(
        custody_service=custody_service,
        hash_service=hash_service,
        template_dir=_template_dir(),
    )
    report = await generator.generate(
        evidence_id,
        _case(),
        evidence_file_path=evidence_file,
    )
    html_doc = await generator.export_html(report)

    assert "<table>" in html_doc
    assert "Alice" in html_doc and "Bob" in html_doc
    assert "acquired" in html_doc.lower() or "ACQUIRED" in html_doc
    assert report.hash_set.md5 in html_doc
    assert report.hash_set.sha1 in html_doc
    assert report.hash_set.sha256 in html_doc
