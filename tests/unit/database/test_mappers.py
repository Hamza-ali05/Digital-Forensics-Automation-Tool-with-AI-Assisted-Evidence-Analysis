"""Unit tests for ORM ↔ domain mappers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dfat.core.enums import (
    ArtefactCategory,
    EvidenceType,
    HashAlgorithm,
    PipelineStage,
    SuspicionLevel,
)
from dfat.core.models.artefact import Artefact, RankedArtefact
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata, EvidenceImage, MemoryDump
from dfat.core.models.pipeline import AuditEntry
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.database.mappers import (
    artefact_domain_to_orm,
    artefact_orm_to_domain,
    audit_domain_to_orm,
    audit_orm_to_domain,
    benchmark_domain_to_orm,
    benchmark_orm_to_domain,
    evidence_domain_to_orm,
    evidence_orm_to_domain,
    report_domain_to_orm,
    report_orm_to_domain,
    usability_domain_to_orm,
    usability_orm_to_domain,
)


def test_evidence_orm_to_domain_roundtrip() -> None:
    """EvidenceImage maps to ORM and back with stable identity fields."""
    # Arrange
    case = CaseMetadata(
        case_id="case-1",
        case_name="Case",
        investigator="Inv",
        description="Desc",
    )
    domain = EvidenceImage(
        evidence_id="ev-1",
        file_path=Path("/tmp/sample.dd"),
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=10,
        acquired_at=datetime(2024, 1, 1, tzinfo=UTC),
        case=case,
    )

    # Act
    orm = evidence_domain_to_orm(domain, registered_by="user-1")
    restored = evidence_orm_to_domain(orm)

    # Assert
    assert restored.evidence_id == domain.evidence_id
    assert restored.original_hash == domain.original_hash
    assert restored.case.case_id == domain.case.case_id
    assert restored.evidence_type is EvidenceType.DISK_IMAGE


def test_evidence_mapper_handles_memory_dump() -> None:
    """MemoryDump volatility profile survives an ORM roundtrip."""
    # Arrange
    case = CaseMetadata(case_id="case-m", case_name="Mem", investigator="Inv")
    domain = MemoryDump(
        evidence_id="ev-mem",
        file_path=Path("/tmp/mem.raw"),
        evidence_type=EvidenceType.MEMORY_DUMP,
        original_hash="b" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=20,
        acquired_at=datetime(2024, 1, 2, tzinfo=UTC),
        case=case,
        volatility_profile="Win10x64",
    )

    # Act
    orm = evidence_domain_to_orm(domain)
    restored = evidence_orm_to_domain(orm)

    # Assert
    assert isinstance(restored, MemoryDump)
    assert restored.volatility_profile == "Win10x64"
    assert restored.evidence_type is EvidenceType.MEMORY_DUMP


def test_artefact_orm_to_domain_roundtrip() -> None:
    """Artefact (and ranked) fields roundtrip through ORM mapping."""
    # Arrange
    domain = RankedArtefact(
        artefact_id="art-1",
        category=ArtefactCategory.BROWSER_HISTORY,
        source_evidence_id="ev-1",
        raw_data={"url": "http://x"},
        parsed_at=datetime(2024, 1, 3, tzinfo=UTC),
        source_path="History",
        suspicion_level=SuspicionLevel.HIGH,
        relevance_score=0.9,
        classification_reasoning="match",
    )

    # Act
    orm = artefact_domain_to_orm(domain, evidence_id="ev-1")
    restored = artefact_orm_to_domain(orm)

    # Assert
    assert isinstance(restored, RankedArtefact)
    assert restored.artefact_id == "art-1"
    assert restored.relevance_score == 0.9
    assert restored.suspicion_level is SuspicionLevel.HIGH


def test_report_orm_to_domain_roundtrip() -> None:
    """ForensicReport envelope roundtrips through ORM mapping."""
    # Arrange
    case = CaseMetadata(case_id="case-r", case_name="R", investigator="Inv")
    domain = ForensicReport(
        report_id="rep-1",
        case=case,
        json_report=JSONReport(
            report_id="json-1",
            evidence_id="ev-1",
            artefact_data=[{"id": 1}],
            integrity_hash="c" * 64,
        ),
        narrative_report=NarrativeReport(
            report_id="narr-1",
            evidence_id="ev-1",
            summary_text="Summary",
            llm_model_used="mock",
        ),
        pipeline_duration_seconds=1.25,
        stage_timings={"parsing": 0.5},
    )

    # Act
    orm = report_domain_to_orm(domain)
    restored = report_orm_to_domain(orm)

    # Assert
    assert restored.report_id == "rep-1"
    assert restored.json_report.integrity_hash == "c" * 64
    assert restored.narrative_report.summary_text == "Summary"
    assert restored.pipeline_duration_seconds == 1.25


def test_benchmark_orm_to_domain_roundtrip() -> None:
    """BenchmarkResult metrics roundtrip through ORM mapping."""
    # Arrange
    domain = BenchmarkResult(
        benchmark_id="bench-1",
        dataset_name="dfrws",
        precision=0.8,
        recall=0.7,
        f1_score=0.75,
        time_to_triage_seconds=12.0,
        artefacts_expected=10,
        artefacts_recovered=8,
        false_positives=2,
        false_negatives=2,
        evaluated_at=datetime(2024, 1, 4, tzinfo=UTC),
    )

    # Act
    orm = benchmark_domain_to_orm(domain, evidence_id="ev-1")
    restored = benchmark_orm_to_domain(orm)

    # Assert
    assert restored.benchmark_id == "bench-1"
    assert restored.precision == 0.8
    assert restored.f1_score == 0.75


def test_usability_orm_to_domain_roundtrip() -> None:
    """UsabilityResponse ratings roundtrip through ORM mapping."""
    # Arrange
    domain = UsabilityResponse(
        response_id="use-1",
        participant_id="p-1",
        usefulness_rating=5,
        accuracy_rating=4,
        clarity_rating=5,
        free_text_feedback="good",
        submitted_at=datetime(2024, 1, 5, tzinfo=UTC),
    )

    # Act
    orm = usability_domain_to_orm(domain)
    restored = usability_orm_to_domain(orm)

    # Assert
    assert restored.response_id == "use-1"
    assert restored.usefulness_rating == 5
    assert restored.free_text_feedback == "good"


def test_audit_orm_to_domain_roundtrip() -> None:
    """AuditEntry details roundtrip through ORM mapping."""
    # Arrange
    domain = AuditEntry(
        entry_number=3,
        timestamp=datetime(2024, 1, 6, tzinfo=UTC),
        stage=PipelineStage.ACQUISITION,
        action="TEST",
        evidence_id="ev-1",
        details={"k": "v"},
    )

    # Act
    orm = audit_domain_to_orm(domain, user_id="user-1", ip_address="127.0.0.1")
    restored = audit_orm_to_domain(orm)

    # Assert
    assert restored.entry_number == 3
    assert restored.action == "TEST"
    assert restored.details == {"k": "v"}
    assert restored.stage is PipelineStage.ACQUISITION
