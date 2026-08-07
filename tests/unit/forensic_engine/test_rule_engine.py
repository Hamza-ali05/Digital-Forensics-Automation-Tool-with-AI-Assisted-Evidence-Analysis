"""Unit tests for RuleBasedTriageEngine."""

from __future__ import annotations

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.processing.ioc_detector import IOCMatch
from dfat.forensic_engine.processing.relationship_mapper import RelationshipMap
from dfat.forensic_engine.triage.rule_engine import RuleBasedTriageEngine
from dfat.forensic_engine.triage.rules import TriageRule
from dfat.forensic_engine.triage.scoring import ScoringEngine


def test_evaluate_returns_ranked_artefacts() -> None:
    """Verify default rules produce RankedArtefact output."""
    # Arrange
    artefact = Artefact(
        artefact_id="f1",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id="ev-1",
        raw_data={
            "filename": "evil.exe",
            "path": "/Temp/evil.exe",
            "size": 10,
            "is_deleted": True,
            "file_type": "deleted",
        },
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[artefact],
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )
    engine = RuleBasedTriageEngine(ScoringEngine())

    # Act
    ranked = engine.evaluate(artefact_set, [], RelationshipMap())

    # Assert
    assert len(ranked) == 1
    assert ranked[0].artefact_id == "f1"
    assert ranked[0].relevance_score >= 0.0
    assert ranked[0].suspicion_level is not None
    assert ranked[0].classification_reasoning


def test_evaluate_applies_custom_rule_boost() -> None:
    """Verify matching custom rules increase relevance score."""
    # Arrange
    artefact = Artefact(
        artefact_id="p1",
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-1",
        raw_data={"pid": 1, "name": "normal.exe"},
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[artefact],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )
    rule = TriageRule(
        rule_id="test-name-equals",
        name="Name equals normal",
        description="boosted",
        category=ArtefactCategory.RUNNING_PROCESS,
        condition_field="name",
        condition_operator="equals",
        condition_value="normal.exe",
        suspicion_boost=0.5,
    )
    engine = RuleBasedTriageEngine(ScoringEngine(), rules=[rule])

    # Act
    ranked = engine.evaluate(artefact_set, [], RelationshipMap())

    # Assert
    assert ranked[0].relevance_score >= 0.5
    assert "Name equals normal" in (ranked[0].classification_reasoning or "")


def test_evaluate_sorts_critical_first() -> None:
    """Verify CRITICAL artefacts sort ahead of informational ones."""
    # Arrange
    low = Artefact(
        artefact_id="low",
        category=ArtefactCategory.BROWSER_HISTORY,
        source_evidence_id="ev-1",
        raw_data={
            "url": "https://example.com",
            "title": "x",
            "visit_count": 1,
            "browser_type": "chrome",
        },
    )
    high = Artefact(
        artefact_id="high",
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={
            "pid": 1,
            "process_name": "x",
            "vad_start": "0x1",
            "protection": "PAGE_EXECUTE_READWRITE",
            "suspicious_indicators": ["MZ header", "RWX memory region"],
        },
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[low, high],
        categories_present=[low.category, high.category],
    )
    iocs = [
        IOCMatch(
            artefact_id="high",
            ioc_type="injection",
            indicator="MZ",
            confidence="high",
            description="injected",
            matched_rule="injected_code",
        )
    ]
    engine = RuleBasedTriageEngine(ScoringEngine())

    # Act
    ranked = engine.evaluate(artefact_set, iocs, RelationshipMap())

    # Assert
    assert ranked[0].artefact_id == "high"
    assert ranked[0].suspicion_level in {SuspicionLevel.HIGH, SuspicionLevel.CRITICAL}


def test_evaluate_empty_set_returns_empty() -> None:
    """Verify empty input yields an empty ranking."""
    # Arrange
    empty = ArtefactSet(evidence_id="ev-1", artefacts=[], categories_present=[])
    engine = RuleBasedTriageEngine(ScoringEngine())

    # Act
    ranked = engine.evaluate(empty, [], RelationshipMap())

    # Assert
    assert ranked == []
