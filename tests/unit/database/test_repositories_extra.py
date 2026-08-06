"""Additional repository coverage for report/user/evaluation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dfat.core.enums import EvidenceType, HashAlgorithm
from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.database.engine import DatabaseEngine
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.evaluation_repo import (
    SQLAlchemyBenchmarkRepository,
    SQLAlchemyUsabilityRepository,
)
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository


@pytest.mark.asyncio
async def test_report_repo_save_get_and_list(
    db_engine: DatabaseEngine,
    sample_case_metadata: CaseMetadata,
) -> None:
    """Report repository persists and retrieves forensic reports."""
    # Arrange
    repo = SQLAlchemyReportRepository(db_engine.session_factory)
    report = ForensicReport(
        report_id="rep-cov-1",
        case=sample_case_metadata,
        json_report=JSONReport(
            report_id="json-cov-1",
            evidence_id="ev-cov-1",
            artefact_data=[],
            integrity_hash="e" * 64,
        ),
        narrative_report=NarrativeReport(
            report_id="narr-cov-1",
            evidence_id="ev-cov-1",
            summary_text="cov",
            llm_model_used="mock",
        ),
        pipeline_duration_seconds=2.0,
        stage_timings={"parsing": 1.0},
    )

    # Act
    await repo.save(report)
    loaded = await repo.get("rep-cov-1")
    by_case = await repo.get_by_case(sample_case_metadata.case_id)
    listed = await repo.list_all()

    # Assert
    assert loaded is not None
    assert loaded.report_id == "rep-cov-1"
    assert any(item.report_id == "rep-cov-1" for item in by_case)
    assert any(item.report_id == "rep-cov-1" for item in listed)


@pytest.mark.asyncio
async def test_evidence_repo_get_by_case_and_hash(
    db_engine: DatabaseEngine,
    tmp_path: Path,
) -> None:
    """Evidence repository supports case and hash lookups."""
    # Arrange
    path = tmp_path / "hash.dd"
    path.write_bytes(b"hash")
    repo = SQLAlchemyEvidenceRepository(db_engine.session_factory)
    evidence = EvidenceImage(
        evidence_id="ev-hash-1",
        file_path=path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="f" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=4,
        acquired_at=datetime(2024, 1, 1, tzinfo=UTC),
        case=CaseMetadata(case_id="case-hash", case_name="H", investigator="I"),
    )
    await repo.save(evidence)

    # Act
    by_case = await repo.get_by_case("case-hash")
    by_hash = await repo.get_by_hash("f" * 64)

    # Assert
    assert len(by_case) == 1
    assert by_hash is not None
    assert by_hash.evidence_id == "ev-hash-1"


@pytest.mark.asyncio
async def test_user_repo_lookup_helpers(
    db_engine: DatabaseEngine,
    seeded_db: dict,
) -> None:
    """User repository username/email/role lookups work on seeded data."""
    # Arrange
    repo = SQLAlchemyUserRepository(db_engine.session_factory)

    # Act
    admin = await repo.get_by_username("admin")
    by_email = await repo.get_by_email("admin@example.com")
    role = await repo.get_role_by_name("admin")
    users = await repo.list_all()

    # Assert
    assert admin is not None
    assert by_email is not None
    assert role is not None
    assert role.name == "admin"
    assert len(users) >= 3


@pytest.mark.asyncio
async def test_benchmark_and_usability_repos(db_engine: DatabaseEngine) -> None:
    """Benchmark and usability repositories persist evaluation artefacts."""
    # Arrange
    bench_repo = SQLAlchemyBenchmarkRepository(db_engine.session_factory)
    use_repo = SQLAlchemyUsabilityRepository(db_engine.session_factory)
    result = BenchmarkResult(
        benchmark_id="bench-cov-1",
        dataset_name="dfrws",
        precision=1.0,
        recall=1.0,
        f1_score=1.0,
        time_to_triage_seconds=1.0,
        artefacts_expected=1,
        artefacts_recovered=1,
        false_positives=0,
        false_negatives=0,
    )
    response = UsabilityResponse(
        response_id="use-cov-1",
        participant_id="p-1",
        usefulness_rating=5,
        accuracy_rating=5,
        clarity_rating=4,
    )

    # Act
    await bench_repo.save(result)
    await use_repo.save(response)
    benches = await bench_repo.list_all()
    uses = await use_repo.get_all_responses()
    by_dataset = await bench_repo.get_by_dataset("dfrws")
    latest = await bench_repo.get_latest("dfrws")
    count = await use_repo.count_responses()

    # Assert
    assert any(item.benchmark_id == "bench-cov-1" for item in benches)
    assert any(item.response_id == "use-cov-1" for item in uses)
    assert by_dataset
    assert latest is not None
    assert count >= 1


@pytest.mark.asyncio
async def test_artefact_repo_list_and_delete(
    db_engine: DatabaseEngine,
    sample_artefact_set: ArtefactSet,
) -> None:
    """Artefact repository can list sets and delete by evidence ID."""
    # Arrange
    repo = SQLAlchemyArtefactRepository(db_engine.session_factory)
    await repo.save(sample_artefact_set)

    # Act
    listed = await repo.list_all()
    deleted = await repo.delete(sample_artefact_set.evidence_id)
    after = await repo.get(sample_artefact_set.evidence_id)

    # Assert
    assert any(item.evidence_id == sample_artefact_set.evidence_id for item in listed)
    assert deleted is True
    assert after is None


@pytest.mark.asyncio
async def test_report_repo_delete_and_get_by_evidence(
    db_engine: DatabaseEngine,
    sample_case_metadata: CaseMetadata,
) -> None:
    """Report repository supports delete and evidence lookup."""
    repo = SQLAlchemyReportRepository(db_engine.session_factory)
    report = ForensicReport(
        report_id="rep-del-1",
        case=sample_case_metadata,
        json_report=JSONReport(
            report_id="json-del-1",
            evidence_id="ev-del-rep",
            integrity_hash="1" * 64,
        ),
        narrative_report=NarrativeReport(
            report_id="narr-del-1",
            evidence_id="ev-del-rep",
            summary_text="x",
            llm_model_used="mock",
        ),
        pipeline_duration_seconds=1.0,
    )
    await repo.save(report)

    # Act
    by_evidence = await repo.get_by_evidence("ev-del-rep")
    deleted = await repo.delete("rep-del-1")

    # Assert
    assert by_evidence is not None
    assert deleted is True
