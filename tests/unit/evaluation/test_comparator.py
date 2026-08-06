"""Unit tests for benchmark comparator TP/FP/FN logic."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.metrics import MetricsCalculator


def test_compare_computes_true_positives_for_matching_identifiers(
    mock_audit_logger: MagicMock,
) -> None:
    """Verify matching category::identifier pairs count as true positives."""
    # Arrange
    comparator = BenchmarkComparator(
        MetricsCalculator(),
        mock_audit_logger,
        {"precision_min": 0.0, "recall_min": 0.0, "f1_min": 0.0},
    )
    recovered = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[
            Artefact(
                category=ArtefactCategory.RUNNING_PROCESS,
                source_evidence_id="ev-1",
                raw_data={"name": "mimikatz.exe", "identifier": "mimikatz.exe"},
            ),
            Artefact(
                category=ArtefactCategory.BROWSER_HISTORY,
                source_evidence_id="ev-1",
                raw_data={"url": "http://noise.example", "identifier": "http://noise.example"},
            ),
        ],
        categories_present=[
            ArtefactCategory.RUNNING_PROCESS,
            ArtefactCategory.BROWSER_HISTORY,
        ],
    )
    ground_truth = {
        "dataset_name": "unit_gt",
        "artefacts": [
            {"category": "running_process", "identifier": "mimikatz.exe"},
            {"category": "event_log", "identifier": "4688"},
        ],
    }
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 10, tzinfo=UTC)

    # Act
    result = comparator.compare(recovered, ground_truth, start, end)

    # Assert
    # TP=1 (mimikatz), FP=1 (noise), FN=1 (4688)
    assert result.artefacts_recovered == 2
    assert result.false_positives == 1
    assert result.false_negatives == 1
    assert result.precision == 0.5
    assert result.recall == 0.5


def test_compare_handles_empty_recovered_set(mock_audit_logger: MagicMock) -> None:
    """Verify empty recovery yields zero precision and zero recall."""
    # Arrange
    comparator = BenchmarkComparator(
        MetricsCalculator(),
        mock_audit_logger,
        {"precision_min": 0.0, "recall_min": 0.0, "f1_min": 0.0},
    )
    recovered = ArtefactSet(evidence_id="ev-1", artefacts=[], categories_present=[])
    ground_truth = {
        "dataset_name": "unit_gt",
        "artefacts": [{"category": "running_process", "identifier": "mimikatz.exe"}],
    }
    now = datetime(2024, 1, 1, tzinfo=UTC)

    # Act
    result = comparator.compare(recovered, ground_truth, now, now)

    # Assert
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.false_negatives == 1


def test_generate_comparison_report_includes_pass_flag(
    mock_audit_logger: MagicMock,
) -> None:
    """Verify comparison report includes threshold pass/fail."""
    # Arrange
    comparator = BenchmarkComparator(
        MetricsCalculator(),
        mock_audit_logger,
        {"precision_min": 0.9, "recall_min": 0.9, "f1_min": 0.9},
    )
    recovered = ArtefactSet(evidence_id="ev-1", artefacts=[], categories_present=[])
    ground_truth = {"dataset_name": "unit_gt", "artefacts": []}
    now = datetime(2024, 1, 1, tzinfo=UTC)
    result = comparator.compare(recovered, ground_truth, now, now)

    # Act
    report = comparator.generate_comparison_report(result)

    # Assert
    assert "pass" in report
    assert report["dataset_name"] == "unit_gt"
