"""Unit tests for StageRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dfat.core.enums import PipelineStage
from dfat.pipeline.stage_registry import StageRegistry


def _stage(name: PipelineStage) -> MagicMock:
    """Build a minimal IPipelineStage mock."""
    stage = MagicMock()
    stage.stage_name = name
    stage.description = f"{name.value} stage"
    return stage


def test_register_and_get_ordered_full_mode() -> None:
    """Verify full mode returns all five stages in pipeline order."""
    # Arrange
    registry = StageRegistry()
    for name in (
        PipelineStage.EVALUATION,
        PipelineStage.ACQUISITION,
        PipelineStage.REPORTING,
        PipelineStage.PARSING,
        PipelineStage.AI_TRIAGE,
    ):
        registry.register(_stage(name))

    # Act
    ordered = registry.get_ordered_stages("full")

    # Assert
    assert [s.stage_name for s in ordered] == [
        PipelineStage.ACQUISITION,
        PipelineStage.PARSING,
        PipelineStage.AI_TRIAGE,
        PipelineStage.REPORTING,
        PipelineStage.EVALUATION,
    ]
    assert registry.is_registered(PipelineStage.PARSING)
    assert len(registry.list_registered()) == 5


def test_parse_only_and_triage_only_modes() -> None:
    """Verify mode-specific stage subsets."""
    # Arrange
    registry = StageRegistry()
    for name in (
        PipelineStage.ACQUISITION,
        PipelineStage.PARSING,
        PipelineStage.AI_TRIAGE,
    ):
        registry.register(_stage(name))

    # Act / Assert
    assert [s.stage_name for s in registry.get_ordered_stages("parse-only")] == [
        PipelineStage.ACQUISITION,
        PipelineStage.PARSING,
    ]
    assert [s.stage_name for s in registry.get_ordered_stages("triage-only")] == [
        PipelineStage.AI_TRIAGE,
    ]


def test_unknown_mode_and_missing_stage_raise() -> None:
    """Verify ValueError for unknown mode and KeyError for missing stage."""
    # Arrange
    registry = StageRegistry()
    registry.register(_stage(PipelineStage.ACQUISITION))

    # Act / Assert
    with pytest.raises(ValueError, match="Unknown pipeline mode"):
        registry.get_ordered_stages("bogus")
    with pytest.raises(KeyError):
        registry.get(PipelineStage.PARSING)
    with pytest.raises(KeyError):
        registry.get_ordered_stages("parse-only")
