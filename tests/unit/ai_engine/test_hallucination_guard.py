"""Unit tests for hallucination mitigation (Prompt 5.20)."""

from __future__ import annotations

from dfat.ai_engine.validation import HallucinationGuard
from dfat.core.enums import ArtefactCategory, SuspicionLevel


def _guard(valid_ids: set[str] | None = None) -> HallucinationGuard:
    return HallucinationGuard(
        valid_artefact_ids=valid_ids or {"art-1"},
        valid_categories={item.value for item in ArtefactCategory},
        valid_suspicion_levels={item.value for item in SuspicionLevel},
        known_facts={"8.8.8.8", "evil.example"},
    )


def test_detects_hallucinated_artefact_ids() -> None:
    """Verify unknown artefact IDs are flagged as hallucinations."""
    report = _guard().check_response(
        "Artefact art-1 is related to art-999 and art-888 via injection."
    )
    assert "art-999" in report.hallucinated_ids
    assert "art-888" in report.hallucinated_ids
    assert "art-1" not in report.hallucinated_ids


def test_detects_fabricated_categories() -> None:
    """Verify fabricated taxonomy terms are flagged."""
    report = _guard().check_response(
        "This malware_signature and rootkit_trace were classified as catastrophic."
    )
    assert "malware_signature" in report.fabricated_terms
    assert "rootkit_trace" in report.fabricated_terms


def test_detects_unsupported_assertions() -> None:
    """Verify overconfident unsupported claims are flagged."""
    report = _guard().check_response(
        "It is clear that the attacker fully compromised the domain controller."
    )
    assert report.unsupported_assertions


def test_clean_response_marks_hallucinations() -> None:
    """Verify clean_response annotates hallucinated IDs."""
    report = _guard().check_response(
        "Artefact art-1 is related to art-999 via injection."
    )
    assert "[HALLUCINATED_ID:art-999]" in report.clean_response


def test_risk_level_assessment() -> None:
    """Verify risk_level reflects hallucination severity."""
    low = _guard().check_response("art-1 shows an RWX region [UNCERTAIN].")
    assert low.risk_level == "low"

    high = _guard().check_response(
        "Definitely art-2 and art-3 prove malware_signature catastrophic compromise."
    )
    assert high.risk_level in {"medium", "high"}
