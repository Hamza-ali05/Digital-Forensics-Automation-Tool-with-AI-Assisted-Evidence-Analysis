"""Unit tests for hallucination detection and response validation (Prompt 5.12)."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.explanation import ArtefactExplanation, ConfidenceScorer
from dfat.ai_engine.summarization import SummaryResult
from dfat.ai_engine.validation import (
    AIResponseValidator,
    HallucinationGuard,
)
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, RankedArtefact


def _guard(valid_ids: set[str] | None = None) -> HallucinationGuard:
    return HallucinationGuard(
        valid_artefact_ids=valid_ids or {"art-1"},
        valid_categories={item.value for item in ArtefactCategory},
        valid_suspicion_levels={item.value for item in SuspicionLevel},
        known_facts={"8.8.8.8", "evil.example"},
    )


def test_hallucinated_artefact_ids_detected() -> None:
    report = _guard().check_response(
        "Artefact art-1 is related to art-999 and art-888 via injection."
    )
    assert "art-999" in report.hallucinated_ids
    assert "art-888" in report.hallucinated_ids
    assert "art-1" not in report.hallucinated_ids
    assert "[HALLUCINATED_ID:art-999]" in report.clean_response


def test_fabricated_terms_flagged() -> None:
    report = _guard().check_response(
        "This malware_signature and rootkit_trace were classified as catastrophic."
    )
    assert "malware_signature" in report.fabricated_terms
    assert "rootkit_trace" in report.fabricated_terms
    assert "catastrophic" in report.fabricated_terms


def test_unsupported_assertions_identified() -> None:
    report = _guard().check_response(
        "It is clear that the attacker fully compromised the domain controller."
    )
    assert report.unsupported_assertions
    assert any("clear that" in item.lower() for item in report.unsupported_assertions)


def test_risk_level_assessed() -> None:
    low = _guard().check_response("art-1 shows an RWX region [UNCERTAIN].")
    assert low.risk_level == "low"

    high = _guard().check_response(
        "Definitely art-2 and art-3 prove malware_signature catastrophic compromise."
    )
    assert high.risk_level in {"medium", "high"}
    assert high.hallucinated_ids
    assert high.fabricated_terms or high.unsupported_assertions


def test_validator_summary_and_classification() -> None:
    guard = _guard({"art-1"})
    validator = AIResponseValidator(guard, ConfidenceScorer())
    artefact = Artefact(
        artefact_id="art-1",
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={"remote_address": "8.8.8.8"},
    )
    results = [
        ClassificationResult(
            artefact_id="art-1",
            suspicion_level=SuspicionLevel.HIGH,
            reasoning="art-1 contains injected code",
            ioc_indicators=["MZ"],
            raw_llm_response="ok",
        )
    ]
    class_result = validator.validate_classification(results, [artefact])
    assert class_result.hallucination_report is not None
    assert class_result.confidence > 0.0

    summary = SummaryResult(
        full_text=(
            "1. EXECUTIVE SUMMARY\nart-1 overview\n"
            "2. KEY FINDINGS\n- art-1\n"
            "3. TIMELINE OF EVENTS\nn/a\n"
            "4. INDICATORS OF COMPROMISE\n- MZ\n"
            "5. RECOMMENDED NEXT STEPS\n- dump\n"
        ),
        executive_summary="art-1 overview",
        key_findings=["art-1"],
        timeline_narrative="n/a",
        iocs_identified=["MZ"],
        recommended_actions=["dump"],
        model_used="llama3",
        prompt_version="1.0.0",
        generated_at=datetime.now(UTC),
    )
    ranked = [
        RankedArtefact(
            **artefact.model_dump(),
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.8,
        )
    ]
    summary_result = validator.validate_summary(summary, ranked)
    assert summary_result.is_valid is True

    explanation = ArtefactExplanation(
        artefact_id="art-1",
        explanation_text="art-1 represents injected code near 8.8.8.8.",
        forensic_significance="Injected PE",
        suggested_actions=["Dump"],
        confidence=0.8,
        model_used="llama3",
    )
    expl_result = validator.validate_explanation(explanation, ranked[0])
    assert expl_result.is_valid is True
