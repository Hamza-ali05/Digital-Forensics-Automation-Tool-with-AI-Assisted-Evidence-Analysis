"""Unit tests for rule-based triage fallback."""

from __future__ import annotations

from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.core.enums import SuspicionLevel
from dfat.core.models.artefact import ArtefactSet


def test_analyze_ranks_mimikatz_above_informational(
    sample_artefact_set: ArtefactSet,
) -> None:
    """Verify mimikatz.exe is elevated by Prompt 4 rule-based triage."""
    # Arrange
    analyzer = RuleBasedAnalyzer()

    # Act
    ranked = analyzer.analyze(sample_artefact_set)

    # Assert — empty IOC context still triggers PROC-001 (offensive tooling name)
    mimikatz = next(item for item in ranked if "mimikatz" in str(item.raw_data).lower())
    assert mimikatz.suspicion_level != SuspicionLevel.INFORMATIONAL
    assert mimikatz.relevance_score > 0.1
    reasoning = (mimikatz.classification_reasoning or "").lower()
    assert "proc-001" in reasoning or "mimikatz" in reasoning or "suspicious" in reasoning


def test_analyze_returns_one_ranked_item_per_artefact(
    sample_artefact_set: ArtefactSet,
) -> None:
    """Verify every input artefact receives a ranked output."""
    # Arrange
    analyzer = RuleBasedAnalyzer()

    # Act
    ranked = analyzer.analyze(sample_artefact_set)

    # Assert
    assert len(ranked) == sample_artefact_set.total_count


def test_is_available_always_true() -> None:
    """Verify the rule-based analyzer is always available."""
    # Arrange / Act / Assert
    assert RuleBasedAnalyzer().is_available() is True


def test_summarize_produces_non_empty_text(sample_artefact_set: ArtefactSet) -> None:
    """Verify summarize returns a non-empty narrative string."""
    # Arrange
    analyzer = RuleBasedAnalyzer()
    ranked = analyzer.analyze(sample_artefact_set)

    # Act
    summary = analyzer.summarize(ranked)

    # Assert
    assert isinstance(summary, str)
    assert len(summary) > 0
