"""Unit tests for benchmark comparator TP/FP/FN logic (Prompt 6.15)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.dfrws_handler import (
    DFRWSHandler,
    GroundTruth,
    GroundTruthArtefact,
)
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator


def _loader(tmp_path: Path) -> GroundTruthLoader:
    """Build a GroundTruthLoader rooted at ``tmp_path``."""
    return GroundTruthLoader(
        tmp_path,
        DFRWSHandler(tmp_path),
        CFReDSHandler(tmp_path),
    )


def _comparator(
    tmp_path: Path,
    thresholds: dict[str, float] | None = None,
) -> BenchmarkComparator:
    """Build a BenchmarkComparator with mocked persistence/audit."""
    return BenchmarkComparator(
        metrics=MetricsCalculator(),
        ground_truth_loader=_loader(tmp_path),
        audit_service=AsyncMock(),
        benchmark_repo=AsyncMock(),
        thresholds=thresholds
        or {"precision_min": 0.0, "recall_min": 0.0, "f1_min": 0.0},
    )


@pytest.mark.asyncio
async def test_compare_computes_true_positives_for_matching_identifiers(
    tmp_path: Path,
) -> None:
    """Verify matching normalised identifiers count as true positives."""
    comparator = _comparator(tmp_path)
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
                raw_data={
                    "url": "http://noise.example",
                    "identifier": "http://noise.example",
                },
            ),
        ],
        categories_present=[
            ArtefactCategory.RUNNING_PROCESS,
            ArtefactCategory.BROWSER_HISTORY,
        ],
    )
    ground_truth = GroundTruth(
        dataset_name="unit_gt",
        source="DFRWS",
        artefacts=[
            GroundTruthArtefact(
                identifier="running_process::mimikatz.exe",
                category=ArtefactCategory.RUNNING_PROCESS,
                expected_data={"name": "mimikatz.exe"},
            ),
            GroundTruthArtefact(
                identifier="event_log::4688",
                category=ArtefactCategory.EVENT_LOG,
                expected_data={"event_id": "4688"},
            ),
        ],
        categories=[ArtefactCategory.RUNNING_PROCESS, ArtefactCategory.EVENT_LOG],
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 10, tzinfo=UTC)

    result = await comparator.compare(
        recovered, ground_truth, start, end, dataset_name="unit_gt"
    )

    # TP=1 (mimikatz), FP=1 (noise), FN=1 (4688)
    assert result.artefacts_recovered == 2
    assert result.false_positives == 1
    assert result.false_negatives == 1
    assert result.precision == 0.5
    assert result.recall == 0.5
    comparator._benchmark_repo.save.assert_awaited_once()
    comparator._audit_service.log_action.assert_awaited_once()
    assert (
        comparator._audit_service.log_action.await_args.kwargs["action"]
        == "BENCHMARK_EVALUATION_COMPLETED"
    )


@pytest.mark.asyncio
async def test_compare_handles_empty_recovered_set(tmp_path: Path) -> None:
    """Verify empty recovery yields zero precision and zero recall."""
    comparator = _comparator(tmp_path)
    recovered = ArtefactSet(evidence_id="ev-1", artefacts=[], categories_present=[])
    ground_truth = GroundTruth(
        dataset_name="unit_gt",
        source="DFRWS",
        artefacts=[
            GroundTruthArtefact(
                identifier="running_process::mimikatz.exe",
                category=ArtefactCategory.RUNNING_PROCESS,
            ),
        ],
        categories=[ArtefactCategory.RUNNING_PROCESS],
    )
    now = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC)

    result = await comparator.compare(
        recovered, ground_truth, now, end, dataset_name="unit_gt"
    )

    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.false_negatives == 1


@pytest.mark.asyncio
async def test_compare_per_category_is_independent(tmp_path: Path) -> None:
    """Verify per-category metrics do not bleed across categories."""
    comparator = _comparator(tmp_path)
    recovered = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[
            Artefact(
                category=ArtefactCategory.RUNNING_PROCESS,
                source_evidence_id="ev-1",
                raw_data={"name": "mimikatz.exe"},
            ),
            Artefact(
                category=ArtefactCategory.BROWSER_HISTORY,
                source_evidence_id="ev-1",
                raw_data={"url": "http://noise.example"},
            ),
        ],
        categories_present=[
            ArtefactCategory.RUNNING_PROCESS,
            ArtefactCategory.BROWSER_HISTORY,
        ],
    )
    ground_truth = GroundTruth(
        dataset_name="unit_gt",
        source="DFRWS",
        artefacts=[
            GroundTruthArtefact(
                identifier="running_process::mimikatz.exe",
                category=ArtefactCategory.RUNNING_PROCESS,
            ),
            GroundTruthArtefact(
                identifier="browser_history::http://expected.example",
                category=ArtefactCategory.BROWSER_HISTORY,
            ),
        ],
        categories=[
            ArtefactCategory.RUNNING_PROCESS,
            ArtefactCategory.BROWSER_HISTORY,
        ],
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 5, tzinfo=UTC)

    per_category = await comparator.compare_per_category(
        recovered, ground_truth, start, end
    )

    assert per_category["running_process"].precision == 1.0
    assert per_category["running_process"].recall == 1.0
    assert per_category["browser_history"].precision == 0.0
    assert per_category["browser_history"].recall == 0.0
    assert per_category["browser_history"].false_positives == 1
    assert per_category["browser_history"].false_negatives == 1
    comparator._benchmark_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_generate_comparison_report_lists_fp_fn_and_pass(
    tmp_path: Path,
) -> None:
    """Verify report lists FP/FN identifiers and includes pass/fail."""
    comparator = _comparator(
        tmp_path,
        {"precision_min": 0.9, "recall_min": 0.9, "f1_min": 0.9},
    )
    recovered = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[
            Artefact(
                category=ArtefactCategory.BROWSER_HISTORY,
                source_evidence_id="ev-1",
                raw_data={"url": "http://noise.example"},
            ),
        ],
        categories_present=[ArtefactCategory.BROWSER_HISTORY],
    )
    ground_truth = GroundTruth(
        dataset_name="unit_gt",
        source="DFRWS",
        artefacts=[
            GroundTruthArtefact(
                identifier="running_process::mimikatz.exe",
                category=ArtefactCategory.RUNNING_PROCESS,
            ),
        ],
        categories=[ArtefactCategory.RUNNING_PROCESS],
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC)
    result = await comparator.compare(
        recovered, ground_truth, start, end, dataset_name="unit_gt"
    )
    per_category = await comparator.compare_per_category(
        recovered, ground_truth, start, end
    )

    report = comparator.generate_comparison_report(result, per_category)

    assert report["dataset_name"] == "unit_gt"
    assert report["pass"] is False
    assert report["false_positives"]
    assert report["false_negatives"]
    assert "running_process" in report["per_category"]
    assert "browser_history" in report["per_category"]


def _ids(*names: str) -> list[GroundTruthArtefact]:
    return [
        GroundTruthArtefact(
            identifier=f"running_process::{name}",
            category=ArtefactCategory.RUNNING_PROCESS,
            expected_data={"name": name},
        )
        for name in names
    ]


@pytest.mark.asyncio
async def test_perfect_match(tmp_path: Path) -> None:
    """Verify all artefacts recovered yields P=R=F1=1.0."""
    names = [f"proc{i}.exe" for i in range(5)]
    recovered = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[
            Artefact(
                category=ArtefactCategory.RUNNING_PROCESS,
                source_evidence_id="ev-1",
                raw_data={"name": name},
            )
            for name in names
        ],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )
    ground_truth = GroundTruth(
        dataset_name="unit_gt",
        source="DFRWS",
        artefacts=_ids(*names),
        categories=[ArtefactCategory.RUNNING_PROCESS],
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 5, tzinfo=UTC)
    result = await _comparator(tmp_path).compare(
        recovered, ground_truth, start, end, dataset_name="unit_gt"
    )
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1_score == 1.0
    assert result.false_positives == 0
    assert result.false_negatives == 0


@pytest.mark.asyncio
async def test_partial_match(tmp_path: Path) -> None:
    """Verify TP=4, FP=1, FN=1 → P=0.8, R=0.8."""
    expected = [f"proc{i}.exe" for i in range(5)]
    recovered_names = expected[:4] + ["noise.exe"]
    recovered = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[
            Artefact(
                category=ArtefactCategory.RUNNING_PROCESS,
                source_evidence_id="ev-1",
                raw_data={"name": name},
            )
            for name in recovered_names
        ],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )
    ground_truth = GroundTruth(
        dataset_name="unit_gt",
        source="DFRWS",
        artefacts=_ids(*expected),
        categories=[ArtefactCategory.RUNNING_PROCESS],
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 5, tzinfo=UTC)
    result = await _comparator(tmp_path).compare(
        recovered, ground_truth, start, end, dataset_name="unit_gt"
    )
    assert result.precision == 0.8
    assert result.recall == 0.8
    assert abs(result.f1_score - 0.8) < 1e-9
    assert result.false_positives == 1
    assert result.false_negatives == 1


@pytest.mark.asyncio
async def test_no_match(tmp_path: Path) -> None:
    """Verify zero recovery yields P=R=F1=0.0."""
    comparator = _comparator(tmp_path)
    recovered = ArtefactSet(evidence_id="ev-1", artefacts=[], categories_present=[])
    ground_truth = GroundTruth(
        dataset_name="unit_gt",
        source="DFRWS",
        artefacts=_ids("mimikatz.exe"),
        categories=[ArtefactCategory.RUNNING_PROCESS],
    )
    now = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC)
    result = await comparator.compare(
        recovered, ground_truth, now, end, dataset_name="unit_gt"
    )
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1_score == 0.0


@pytest.mark.asyncio
async def test_false_positives_listed(tmp_path: Path) -> None:
    """Verify false positives are listed in the comparison report."""
    comparator = _comparator(
        tmp_path,
        {"precision_min": 0.9, "recall_min": 0.9, "f1_min": 0.9},
    )
    recovered = ArtefactSet(
        evidence_id="ev-1",
        artefacts=[
            Artefact(
                category=ArtefactCategory.BROWSER_HISTORY,
                source_evidence_id="ev-1",
                raw_data={"url": "http://noise.example"},
            ),
        ],
        categories_present=[ArtefactCategory.BROWSER_HISTORY],
    )
    ground_truth = GroundTruth(
        dataset_name="unit_gt",
        source="DFRWS",
        artefacts=[
            GroundTruthArtefact(
                identifier="running_process::mimikatz.exe",
                category=ArtefactCategory.RUNNING_PROCESS,
            ),
        ],
        categories=[ArtefactCategory.RUNNING_PROCESS],
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC)
    result = await comparator.compare(
        recovered, ground_truth, start, end, dataset_name="unit_gt"
    )
    per_category = await comparator.compare_per_category(
        recovered, ground_truth, start, end
    )
    report = comparator.generate_comparison_report(result, per_category)
    assert report["false_positives"]
    assert any("noise" in str(item).lower() for item in report["false_positives"])
