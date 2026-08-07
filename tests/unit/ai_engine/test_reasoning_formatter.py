"""Unit tests for explainable reasoning formatter (Prompt 5.15)."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.explanation import ReasoningChainFormatter
from dfat.ai_engine.summarization import SummaryResult
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, RankedArtefact


def test_format_classification_reasoning() -> None:
    formatter = ReasoningChainFormatter()
    artefact = Artefact(
        artefact_id="art-1",
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={"pid": 1},
        source_path="/proc/1",
    )
    result = ClassificationResult(
        artefact_id="art-1",
        suspicion_level=SuspicionLevel.CRITICAL,
        reasoning="RWX region with MZ header [UNCERTAIN]",
        ioc_indicators=["MZ header", "RWX"],
    )
    output = formatter.format_classification_reasoning(result, artefact, 0.82)

    assert "art-1" in output.formatted_text
    assert "CRITICAL" in output.formatted_text
    assert "MZ header" in output.formatted_text
    assert "82%" in output.formatted_text
    assert "art-1" in output.evidence_citations
    assert output.uncertainty_markers
    assert output.confidence == 0.82


def test_format_ranking_and_summary_reasoning() -> None:
    formatter = ReasoningChainFormatter()
    ranked = RankedArtefact(
        artefact_id="art-2",
        category=ArtefactCategory.NETWORK_CONNECTION,
        source_evidence_id="ev-1",
        raw_data={"remote_address": "8.8.8.8"},
        suspicion_level=SuspicionLevel.HIGH,
        relevance_score=0.91,
        classification_reasoning="External C2-like traffic",
    )
    ranking = formatter.format_ranking_reasoning(ranked)
    assert "0.91" in ranking.formatted_text
    assert "HIGH" in ranking.formatted_text

    summary = SummaryResult(
        full_text="summary mentioning art-2",
        executive_summary="Overview of art-2 [UNCERTAIN]",
        key_findings=["art-2 external connection"],
        timeline_narrative="Day 1",
        iocs_identified=["8.8.8.8"],
        recommended_actions=["Block IP"],
        model_used="llama3",
        prompt_version="1.0.0",
        confidence_score=0.7,
        generated_at=datetime.now(UTC),
    )
    explained = formatter.format_summary_reasoning(summary)
    assert "70%" in explained.formatted_text
    assert "Executive Summary" in explained.formatted_text
    assert "art-2" in explained.evidence_citations
    assert explained.model_attribution == "llama3"
