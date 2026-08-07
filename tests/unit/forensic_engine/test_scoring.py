"""Unit tests for ScoringEngine."""

from __future__ import annotations

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.processing.ioc_detector import IOCMatch
from dfat.forensic_engine.processing.relationship_mapper import RelationshipMap
from dfat.forensic_engine.triage.scoring import ScoringEngine


def _artefact(
    artefact_id: str,
    category: ArtefactCategory,
    **raw: object,
) -> Artefact:
    """Build a minimal artefact."""
    return Artefact(
        artefact_id=artefact_id,
        category=category,
        source_evidence_id="ev-1",
        raw_data=dict(raw),
    )


def test_score_applies_category_base() -> None:
    """Verify injected code receives a higher base score than browser history."""
    # Arrange
    injected = _artefact(
        "i1",
        ArtefactCategory.INJECTED_CODE,
        pid=1,
        process_name="x",
        vad_start="0x1",
        protection="RWX",
        suspicious_indicators=[],
    )
    browser = _artefact(
        "b1",
        ArtefactCategory.BROWSER_HISTORY,
        url="https://x",
        title="t",
        visit_count=1,
        browser_type="chrome",
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[injected, browser],
        categories_present=[injected.category, browser.category],
    )

    # Act
    scored = ScoringEngine().score(artefact_set, [], RelationshipMap())

    # Assert
    by_id = {item.artefact.artefact_id: item for item in scored}
    assert by_id["i1"].score > by_id["b1"].score
    assert by_id["i1"].suspicion_level in {
        SuspicionLevel.MEDIUM,
        SuspicionLevel.HIGH,
        SuspicionLevel.CRITICAL,
    }


def test_score_includes_ioc_and_correlation_bonuses() -> None:
    """Verify IOC and relationship edges increase the score."""
    # Arrange
    artefact = _artefact("p1", ArtefactCategory.RUNNING_PROCESS, pid=1, name="x.exe")
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[artefact],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )
    iocs = [
        IOCMatch(
            artefact_id="p1",
            ioc_type="process",
            indicator="x.exe",
            confidence="high",
            description="suspicious",
            matched_rule="suspicious_process",
        )
    ]
    relationships = RelationshipMap(edges=[("p1", "n1", "process_network")])

    # Act
    scored = ScoringEngine().score(artefact_set, iocs, relationships)

    # Assert
    assert len(scored) == 1
    assert scored[0].score >= 0.3  # high IOC alone
    assert any("ioc:" in factor for factor in scored[0].scoring_factors)
    assert any("correlations:" in factor for factor in scored[0].scoring_factors)


def test_to_suspicion_level_thresholds() -> None:
    """Verify numeric score thresholds map to SuspicionLevel."""
    # Act / Assert
    assert ScoringEngine._to_suspicion_level(0.85) is SuspicionLevel.CRITICAL  # noqa: SLF001
    assert ScoringEngine._to_suspicion_level(0.65) is SuspicionLevel.HIGH  # noqa: SLF001
    assert ScoringEngine._to_suspicion_level(0.45) is SuspicionLevel.MEDIUM  # noqa: SLF001
    assert ScoringEngine._to_suspicion_level(0.25) is SuspicionLevel.LOW  # noqa: SLF001
    assert ScoringEngine._to_suspicion_level(0.1) is SuspicionLevel.INFORMATIONAL  # noqa: SLF001


def test_score_clamps_to_unit_interval() -> None:
    """Verify stacked bonuses never exceed 1.0."""
    # Arrange
    artefact = _artefact(
        "i1",
        ArtefactCategory.INJECTED_CODE,
        pid=1,
        process_name="x",
        vad_start="0x1",
        protection="RWX",
        suspicious_indicators=["MZ"],
        create_time="2024-01-01T00:00:00+00:00",
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[artefact],
        categories_present=[ArtefactCategory.INJECTED_CODE],
    )
    iocs = [
        IOCMatch(
            artefact_id="i1",
            ioc_type="injection",
            indicator="MZ",
            confidence="high",
            description="injected",
            matched_rule="injected_code",
        ),
        IOCMatch(
            artefact_id="i1",
            ioc_type="injection",
            indicator="RWX",
            confidence="high",
            description="rwx",
            matched_rule="rwx_region",
        ),
        IOCMatch(
            artefact_id="i1",
            ioc_type="injection",
            indicator="shellcode",
            confidence="high",
            description="sc",
            matched_rule="shellcode",
        ),
    ]
    relationships = RelationshipMap(
        edges=[("i1", "a", "x"), ("i1", "b", "x"), ("i1", "c", "x"), ("i1", "d", "x")]
    )

    # Act
    scored = ScoringEngine().score(artefact_set, iocs, relationships)

    # Assert
    assert 0.0 <= scored[0].score <= 1.0
