"""Unit tests for report integrity verification (Prompt 6.3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dfat.core.enums import HashAlgorithm
from dfat.reporting.integrity import ReportIntegrityVerifier
from dfat.reporting.schema import ReportSchemaValidator
from dfat.shared.hashing import compute_data_hash


def _hash_artefacts(artefacts: list[dict]) -> str:
    """Match StructuredJSONExporter / ReportIntegrityVerifier canonicalisation."""
    canonical = json.dumps(
        artefacts,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return compute_data_hash(canonical.encode("utf-8"), HashAlgorithm.SHA256)


def _report_document(*, artefacts: list[dict] | None = None) -> dict:
    """Build a minimal integrity-checkable report document."""
    if artefacts is None:
        artefacts = [
            {
                "artefact_id": "art-1",
                "category": "injected_code",
                "source_path": None,
                "suspicion_level": "critical",
                "relevance_score": 0.95,
                "raw_data": {"pid": 4242},
                "classification_reasoning": "RWX region",
                "metadata": {},
            }
        ]
    return {
        "schema_version": "1.0.0",
        "report_id": str(uuid4()),
        "evidence_id": "ev-integrity-001",
        "case_metadata": {
            "case_id": "case-1",
            "case_name": "Integrity Case",
            "investigator": "Analyst",
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "integrity_hash": _hash_artefacts(artefacts),
        "pipeline_stage_timings": {
            "acquisition_seconds": 1.0,
            "parsing_seconds": 1.0,
            "triage_seconds": 1.0,
            "reporting_seconds": 0.5,
        },
        "artefacts": artefacts,
        "summary_statistics": {
            "total_artefacts": len(artefacts),
            "by_category": {"injected_code": len(artefacts)},
            "by_suspicion_level": {"critical": len(artefacts)},
        },
        "ai_metadata": {
            "model_used": "none",
            "prompt_version": "1.0.0",
            "confidence_score": 0.0,
            "analysis_mode": "rule_based",
            "disclaimer": "Advisory only.",
        },
    }


def test_unmodified_report_passes_verification() -> None:
    """Verify an unmodified report passes all integrity checks."""
    document = _report_document()
    result = ReportIntegrityVerifier().verify_report(document)
    assert result.is_valid is True
    assert result.integrity_hash_match is True
    assert result.schema_version_valid is True
    assert result.report_id_valid is True
    assert result.issues == []


def test_altered_artefact_data_fails_verification() -> None:
    """Verify tampering with artefact data fails the integrity hash check."""
    document = _report_document()
    document["artefacts"][0]["raw_data"] = {"pid": 9999, "tampered": True}
    result = ReportIntegrityVerifier().verify_report(document)
    assert result.is_valid is False
    assert result.integrity_hash_match is False
    assert result.schema_version_valid is True
    assert result.report_id_valid is True
    assert any("integrity_hash" in issue for issue in result.issues)


def test_invalid_report_id_fails_verification() -> None:
    """Verify a non-UUID report_id is rejected."""
    document = _report_document()
    document["report_id"] = "not-a-uuid"
    result = ReportIntegrityVerifier().verify_report(document)
    assert result.is_valid is False
    assert result.report_id_valid is False
    assert result.integrity_hash_match is True


def test_verify_report_file_round_trip(tmp_path: Path) -> None:
    """Verify loading a report from disk delegates to verify_report."""
    document = _report_document()
    path = tmp_path / "report.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    result = ReportIntegrityVerifier().verify_report_file(path)
    assert result.is_valid is True
    assert result.integrity_hash_match is True


def test_embed_audit_metadata_fields() -> None:
    """Verify audit metadata is embedded with the expected fields."""
    document = _report_document()
    verifier = ReportIntegrityVerifier()
    enriched = verifier.embed_audit_metadata(
        document,
        user_id="user-42",
        pipeline_job_id="job-7",
        evidence_custody_chain_length=3,
        tool_version="0.1.0",
    )
    audit = enriched["audit_metadata"]
    assert audit["generated_by_user_id"] == "user-42"
    assert audit["pipeline_job_id"] == "job-7"
    assert audit["custody_chain_entries"] == 3
    assert audit["tool_version"] == "0.1.0"
    assert isinstance(audit["generation_host"], str) and audit["generation_host"]
    assert isinstance(audit["generation_timestamp"], str)
    # Original document is not mutated.
    assert "audit_metadata" not in document
    # Hash still verifies after embedding (artefacts unchanged).
    result = verifier.verify_report(enriched)
    assert result.is_valid is True
    assert ReportSchemaValidator().validate(enriched).is_valid is True


# Prompt 6.20 named coverage aliases
test_tampered_artefact_fails_verification = test_altered_artefact_data_fails_verification
test_audit_metadata_embedded = test_embed_audit_metadata_fields
test_file_verification_works = test_verify_report_file_round_trip

