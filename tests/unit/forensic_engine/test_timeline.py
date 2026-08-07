"""Unit tests for TimelineGenerator."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.processing.timeline import TimelineGenerator


def test_generate_orders_entries_chronologically() -> None:
    """Verify timestamped artefacts produce ascending timeline entries."""
    # Arrange
    artefacts = [
        Artefact(
            artefact_id="late",
            category=ArtefactCategory.EVENT_LOG,
            source_evidence_id="ev-1",
            raw_data={
                "event_id": 1,
                "message": "late",
                "is_security_relevant": False,
                "timestamp": "2024-01-02T12:00:00+00:00",
            },
        ),
        Artefact(
            artefact_id="early",
            category=ArtefactCategory.RUNNING_PROCESS,
            source_evidence_id="ev-1",
            raw_data={
                "pid": 1,
                "name": "a.exe",
                "create_time": "2024-01-01T08:00:00+00:00",
            },
        ),
    ]
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=artefacts,
        categories_present=[ArtefactCategory.EVENT_LOG, ArtefactCategory.RUNNING_PROCESS],
    )

    # Act
    timeline = TimelineGenerator().generate(artefact_set)

    # Assert
    assert timeline.entry_count >= 2
    assert timeline.entries[0].timestamp <= timeline.entries[-1].timestamp
    assert timeline.earliest is not None
    assert timeline.latest is not None
    assert timeline.duration_seconds > 0


def test_generate_empty_set_has_zero_duration() -> None:
    """Verify empty artefact sets yield an empty timeline."""
    # Arrange
    empty = ArtefactSet(evidence_id="ev-1", artefacts=[], categories_present=[])

    # Act
    timeline = TimelineGenerator().generate(empty)

    # Assert
    assert timeline.entry_count == 0
    assert timeline.duration_seconds == 0.0
    assert timeline.windows == []


def test_generate_groups_into_windows() -> None:
    """Verify window_seconds groups nearby events."""
    # Arrange
    artefacts = [
        Artefact(
            artefact_id=f"a{i}",
            category=ArtefactCategory.EVENT_LOG,
            source_evidence_id="ev-1",
            raw_data={
                "event_id": i,
                "message": "m",
                "is_security_relevant": False,
                "timestamp": datetime(2024, 1, 1, i, 0, tzinfo=UTC).isoformat(),
            },
        )
        for i in (1, 2, 5)
    ]
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=artefacts,
        categories_present=[ArtefactCategory.EVENT_LOG],
    )

    # Act
    timeline = TimelineGenerator(window_seconds=3600).generate(artefact_set)

    # Assert
    assert timeline.entry_count == 3
    assert len(timeline.windows) >= 1
    assert sum(len(window.entries) for window in timeline.windows) == 3


def test_generate_ignores_artefacts_without_timestamps() -> None:
    """Verify artefacts lacking known timestamp fields are skipped."""
    # Arrange
    artefact = Artefact(
        category=ArtefactCategory.REGISTRY_KEY,
        source_evidence_id="ev-1",
        raw_data={
            "hive_name": "SAM",
            "key_path": "X",
            "value_name": "Y",
            "value_data": "Z",
            "value_type": "RegSZ",
        },
    )
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[artefact],
        categories_present=[ArtefactCategory.REGISTRY_KEY],
    )

    # Act
    timeline = TimelineGenerator().generate(artefact_set)

    # Assert
    assert timeline.entry_count == 0
