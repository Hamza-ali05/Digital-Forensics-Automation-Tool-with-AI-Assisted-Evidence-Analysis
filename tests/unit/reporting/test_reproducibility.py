"""Unit tests for reproducibility verification (Prompt 6.10)."""

from __future__ import annotations

import copy
import json

from dfat.core.enums import HashAlgorithm
from dfat.reporting.reproducibility import (
    ReproducibilityResult,
    ReproducibilityVerifier,
)
from dfat.shared.hashing import compute_data_hash


def _hash(artefacts: list[dict]) -> str:
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
            "artefact_id": "art-1",
            "category": "injected_code",
            "suspicion_level": "critical",
            "relevance_score": 0.99,
            "raw_data": {"pid": 1},
        },
        {
            "artefact_id": "art-2",
            "category": "registry_key",
            "suspicion_level": "high",
            "relevance_score": 0.8,
            "raw_data": {"key": "Run"},
        },
    ]


def _report(artefacts: list[dict] | None = None) -> dict:
    rows = artefacts if artefacts is not None else _artefacts()
    return {
        "schema_version": "1.0.0",
        "report_id": "11111111-1111-1111-1111-111111111111",
        "evidence_id": "ev-repro-1",
        "integrity_hash": _hash(rows),
        "artefacts": rows,
    }


def test_identical_reports_are_reproducible() -> None:
    """Verify two reports from identical artefact input are reproducible."""
    report_a = _report()
    report_b = _report()
    # Different envelope metadata must not affect reproducibility.
    report_b["report_id"] = "22222222-2222-2222-2222-222222222222"
    report_b["generated_at"] = "2099-01-01T00:00:00Z"

    result = ReproducibilityVerifier().compare_reports(report_a, report_b)

    assert isinstance(result, ReproducibilityResult)
    assert result.is_reproducible is True
    assert result.hashes_match is True
    assert result.artefact_count_match is True
    assert result.category_distribution_match is True
    assert result.suspicion_distribution_match is True
    assert result.differences == []
    assert result.hash_a == result.hash_b == report_a["integrity_hash"]


def test_altered_reports_produce_detailed_diff() -> None:
    """Verify altered artefact data fails reproducibility with field diffs."""
    report_a = _report()
    altered = copy.deepcopy(_artefacts())
    altered[0]["raw_data"] = {"pid": 999, "tampered": True}
    altered[0]["suspicion_level"] = "low"
    report_b = _report(altered)

    result = ReproducibilityVerifier().compare_reports(report_a, report_b)

    assert result.is_reproducible is False
    assert result.hashes_match is False
    assert result.artefact_count_match is True
    assert any("integrity_hash mismatch" in item for item in result.differences)
    assert any("art-1.raw_data" in item for item in result.differences)
    assert any("art-1.suspicion_level" in item for item in result.differences)


def test_missing_artefact_is_reported_in_diff() -> None:
    """Verify artefacts present in only one report are listed in differences."""
    report_a = _report()
    reduced = [_artefacts()[0]]
    report_b = _report(reduced)

    result = ReproducibilityVerifier().compare_reports(report_a, report_b)

    assert result.is_reproducible is False
    assert result.artefact_count_match is False
    assert any("only in report A: art-2" in item for item in result.differences)


def test_verify_determinism_true_for_canonical_report() -> None:
    """Verify determinism check passes when stored hash matches reserialisation."""
    report = _report()
    assert ReproducibilityVerifier().verify_determinism(report) is True


def test_verify_determinism_false_when_hash_wrong() -> None:
    """Verify determinism check fails when integrity_hash is incorrect."""
    report = _report()
    report["integrity_hash"] = "0" * 64
    assert ReproducibilityVerifier().verify_determinism(report) is False


# Prompt 6.20 named coverage
test_identical_input_reproducible = test_identical_reports_are_reproducible
test_diff_identifies_changes = test_altered_reports_produce_detailed_diff


def test_different_input_not_reproducible() -> None:
    """Verify different artefact inputs are not reproducible."""
    report_a = _report()
    altered = [
        {
            "artefact_id": "art-x",
            "category": "event_log",
            "suspicion_level": "low",
            "relevance_score": 0.1,
            "raw_data": {"event_id": "1"},
        }
    ]
    report_b = _report(altered)
    result = ReproducibilityVerifier().compare_reports(report_a, report_b)
    assert result.is_reproducible is False
    assert result.hashes_match is False

