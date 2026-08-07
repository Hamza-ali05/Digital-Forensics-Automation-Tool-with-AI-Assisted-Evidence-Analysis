"""Unit tests for AI confidence scoring (Prompt 5.11)."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.explanation import ArtefactExplanation, ConfidenceScorer
from dfat.ai_engine.summarization import SummaryResult
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact


def _artefact(artefact_id: str = "art-1") -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={"pid": 42},
    )


def test_detailed_reasoning_with_id_scores_higher_than_vague() -> None:
    scorer = ConfidenceScorer()
    artefact = _artefact("art-1")
    detailed = ClassificationResult(
        artefact_id="art-1",
        suspicion_level=SuspicionLevel.CRITICAL,
        reasoning=(
            "Artefact art-1 shows an RWX memory region with an MZ header, "
            "consistent with injected code."
        ),
        ioc_indicators=["MZ header", "RWX"],
        raw_llm_response="[]",
    )
    vague = ClassificationResult(
        artefact_id="art-1",
        suspicion_level=SuspicionLevel.INFORMATIONAL,
        reasoning="Maybe suspicious.",
        ioc_indicators=[],
    )
    assert scorer.score_classification(detailed, artefact) > scorer.score_classification(
        vague, artefact
    )


def test_missing_reasoning_scores_low() -> None:
    scorer = ConfidenceScorer()
    result = ClassificationResult(
        artefact_id="art-1",
        suspicion_level=SuspicionLevel.HIGH,
        reasoning="Not classified by AI",
    )
    assert scorer.score_classification(result, _artefact()) <= 0.15


def test_hallucinated_artefact_ids_reduce_score() -> None:
    scorer = ConfidenceScorer()
    artefact = _artefact("art-1")
    clean = ClassificationResult(
        artefact_id="art-1",
        suspicion_level=SuspicionLevel.HIGH,
        reasoning="art-1 contains shellcode patterns in the VAD region.",
        ioc_indicators=["shellcode"],
        raw_llm_response="ok",
    )
    hallucinated = ClassificationResult(
        artefact_id="art-1",
        suspicion_level=SuspicionLevel.HIGH,
        reasoning=(
            "art-1 relates to art-999 and art-888 which were also injected "
            "according to this analysis."
        ),
        ioc_indicators=["shellcode"],
        raw_llm_response="ok",
    )
    clean_score = scorer.score_classification(clean, artefact)
    bad_score = scorer.score_classification(hallucinated, artefact)
    assert bad_score < clean_score

    valid, invalid = scorer._check_artefact_id_references(
        hallucinated.reasoning,
        {"art-1"},
    )
    assert valid == 1
    assert invalid >= 2


def test_summary_all_sections_and_no_hallucination_markers() -> None:
    scorer = ConfidenceScorer()
    summary = SummaryResult(
        full_text=(
            "1. EXECUTIVE SUMMARY\nOverview referencing art-1.\n"
            "2. KEY FINDINGS\n- art-1 injected code\n"
            "3. TIMELINE OF EVENTS\nDay one activity.\n"
            "4. INDICATORS OF COMPROMISE\n- MZ header\n"
            "5. RECOMMENDED NEXT STEPS\n- Dump process\n"
        ),
        executive_summary="Overview referencing art-1.",
        key_findings=["art-1 injected code"],
        timeline_narrative="Day one activity.",
        iocs_identified=["MZ header"],
        recommended_actions=["Dump process"],
        model_used="llama3",
        prompt_version="1.0.0",
        confidence_score=0.0,
        generated_at=datetime.now(UTC),
    )
    score = scorer.score_summary(summary, artefact_count=5)
    assert score >= 0.8


def test_explanation_completeness() -> None:
    scorer = ConfidenceScorer()
    rich = ArtefactExplanation(
        artefact_id="art-1",
        explanation_text=(
            "art-1 represents injected code in process memory with RWX "
            "protection and an MZ header."
        ),
        forensic_significance="Injected PE image in unsigned process.",
        suggested_actions=["Dump VAD", "Check parent process"],
        related_artefact_ids=[],
        confidence=0.8,
        model_used="llama3",
    )
    thin = ArtefactExplanation(
        artefact_id="art-1",
        explanation_text="Unclear.",
        forensic_significance="",
        suggested_actions=[],
        confidence=0.2,
        model_used="llama3",
    )
    assert scorer.score_explanation(rich) > scorer.score_explanation(thin)


def test_high_confidence_for_detailed_reasoning() -> None:
    """Verify detailed reasoning with IOCs scores high."""
    scorer = ConfidenceScorer()
    artefact = _artefact("art-1")
    detailed = ClassificationResult(
        artefact_id="art-1",
        suspicion_level=SuspicionLevel.CRITICAL,
        reasoning=(
            "Artefact art-1 shows an RWX memory region with an MZ header, "
            "consistent with injected code."
        ),
        ioc_indicators=["MZ header", "RWX"],
        raw_llm_response="[]",
    )
    assert scorer.score_classification(detailed, artefact) >= 0.5


def test_low_confidence_for_vague_reasoning() -> None:
    """Verify vague/missing reasoning scores low."""
    test_missing_reasoning_scores_low()


def test_artefact_id_references_boost_score() -> None:
    """Verify referencing the real artefact ID boosts confidence vs vague text."""
    test_detailed_reasoning_with_id_scores_higher_than_vague()


def test_hallucinated_ids_reduce_score() -> None:
    """Alias for hallucinated ID penalty."""
    test_hallucinated_artefact_ids_reduce_score()
