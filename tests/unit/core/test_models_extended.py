"""Extended edge-case tests for core Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dfat.case_management.enums import CaseStatus
from dfat.core.enums import (
    ArtefactCategory,
    EvidenceType,
    HashAlgorithm,
    PipelineStage,
    SuspicionLevel,
)
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata, EvidenceImage, MemoryDump
from dfat.core.models.pipeline import PipelineState, StageResult


def _metadata() -> CaseMetadata:
    return CaseMetadata(case_id="case-1", case_name="Edge", investigator="Alice")


def _artefact() -> Artefact:
    return Artefact(
        artefact_id="art-1",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id="ev-1",
        raw_data={},
    )


def test_case_empty_fields_computed_fields_and_round_trip() -> None:
    # Arrange
    case = Case(metadata=_metadata(), status=CaseStatus.CREATED)

    # Act
    restored = Case.model_validate(case.model_dump())

    # Assert
    assert restored.case_id == "case-1"
    assert restored.case_name == "Edge"
    assert restored.evidence_count == 0
    assert restored.investigator_count == 0
    assert restored.notes == restored.tags == []


def test_case_investigator_rejects_invalid_role() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        CaseInvestigator(
            user_id="u1", username="alice", full_name="Alice", role="observer"
        )


def test_evidence_models_optional_fields_and_round_trip(tmp_path) -> None:
    # Arrange
    image = EvidenceImage(
        evidence_id="ev-1",
        file_path=tmp_path / "empty.dd",
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=0,
        acquired_at=None,
        case=_metadata(),
    )
    memory_payload = image.model_dump()
    memory_payload["evidence_type"] = EvidenceType.MEMORY_DUMP
    memory = MemoryDump(
        **memory_payload, volatility_profile=None, capture_timestamp=None
    )

    # Act / Assert
    assert CaseMetadata.model_validate(_metadata().model_dump()).description is None
    assert EvidenceImage.model_validate(image.model_dump()) == image
    assert MemoryDump.model_validate(memory.model_dump()) == memory


def test_artefact_models_empty_set_computed_count_and_round_trip() -> None:
    # Arrange
    empty = ArtefactSet(evidence_id="ev-1")
    artefact = _artefact()
    ranked = RankedArtefact(
        **artefact.model_dump(),
        suspicion_level=SuspicionLevel.LOW,
        relevance_score=0.0,
        classification_reasoning=None,
    )

    # Act / Assert
    assert empty.total_count == 0
    assert empty.categories_present == []
    assert Artefact.model_validate(artefact.model_dump()) == artefact
    assert RankedArtefact.model_validate(ranked.model_dump()) == ranked
    assert ArtefactSet.model_validate(empty.model_dump()).total_count == 0


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_ranked_artefact_rejects_out_of_bounds_score(score: float) -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        RankedArtefact(
            **_artefact().model_dump(),
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=score,
        )


def test_pipeline_state_complete_only_with_every_stage_key() -> None:
    # Arrange
    results = {
        stage.value: StageResult(stage=stage, success=True, duration_seconds=0.0)
        for stage in PipelineStage
    }
    incomplete = PipelineState(
        case=_metadata(),
        current_stage=PipelineStage.ACQUISITION,
        stage_results=dict(list(results.items())[:-1]),
    )
    complete = PipelineState(
        case=_metadata(),
        current_stage=PipelineStage.EVALUATION,
        stage_results=results,
        completed_at=datetime.now(UTC),
    )

    # Act / Assert
    assert incomplete.is_complete is False
    assert complete.is_complete is True
    assert PipelineState.model_validate(complete.model_dump()).is_complete is True


def test_evaluation_models_round_trip_and_optional_ratings(
    sample_benchmark_result: BenchmarkResult,
) -> None:
    # Arrange
    response = UsabilityResponse(
        participant_id="anonymous",
        usefulness_rating=3,
        accuracy_rating=3,
        clarity_rating=3,
    )

    # Act / Assert
    assert BenchmarkResult.model_validate(
        sample_benchmark_result.model_dump()
    ) == sample_benchmark_result
    assert UsabilityResponse.model_validate(response.model_dump()) == response
    assert response.q1_rating is response.q4_rating is response.comparative_rating is None
    assert response.free_text_feedback is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("usefulness_rating", 0), ("accuracy_rating", 6), ("q1_rating", 0), ("q4_rating", 6)],
)
def test_usability_response_rejects_out_of_bounds_likert(
    field: str, value: int
) -> None:
    # Arrange
    payload = {
        "participant_id": "p1",
        "usefulness_rating": 3,
        "accuracy_rating": 3,
        "clarity_rating": 3,
        field: value,
    }

    # Act / Assert
    with pytest.raises(ValidationError):
        UsabilityResponse(**payload)
