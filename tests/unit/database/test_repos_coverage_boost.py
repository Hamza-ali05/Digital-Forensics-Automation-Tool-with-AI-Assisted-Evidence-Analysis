"""Coverage boost for database repositories — happy paths and SQLAlchemyError branches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from dfat.case_management.enums import CaseStatus, CustodyAction, EvidenceStatus
from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, PipelineStage
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.pipeline import AuditEntry
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from dfat.database.engine import DatabaseEngine
from dfat.database.exceptions import DatabaseError
from dfat.database.models.ai_orm import AIAnalysisRecordORM
from dfat.database.models.user import UserORM
from dfat.database.repositories.ai_analysis_repo import SQLAlchemyAIAnalysisRepository
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.base_repo import SQLAlchemyRepository
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.custody_repo import CustodyRepository
from dfat.database.repositories.evaluation_repo import (
    SQLAlchemyBenchmarkRepository,
    SQLAlchemyUsabilityRepository,
)
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.evidence_status_repo import (
    EvidenceMetadataRepository,
    EvidenceStatusRepository,
)
from dfat.database.repositories.report_repo import SQLAlchemyReportRepository
from dfat.database.repositories.session_repo import SessionRepository
from dfat.database.repositories.user_repo import SQLAlchemyUserRepository
from dfat.evidence_management.models import (
    ChainOfCustodyRecord,
    EvidenceMetadataRecord,
    EvidenceStatusChange,
    HashSet,
)


def _failing_session(*, method: str = "execute") -> MagicMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    err = SQLAlchemyError("db boom")
    setattr(session, method, AsyncMock(side_effect=err))
    session.merge = AsyncMock(side_effect=err)
    session.get = AsyncMock(side_effect=err)
    session.execute = AsyncMock(side_effect=err)
    session.add = MagicMock()
    session.delete = AsyncMock(side_effect=err)
    session.commit = AsyncMock(side_effect=err)
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    return MagicMock(return_value=session)


def _case(user_id: str, case_id: str = "case-boost-1") -> Case:
    inv = CaseInvestigator(
        user_id=user_id,
        username="investigator",
        full_name="Lead",
        role="lead",
    )
    return Case(
        metadata=CaseMetadata(
            case_id=case_id, case_name="Boost", investigator="Lead"
        ),
        investigators=[inv],
        lead_investigator_id=user_id,
        status=CaseStatus.CREATED,
    )


def _evidence(tmp_path: Path, case_id: str = "case-boost-1") -> EvidenceImage:
    path = tmp_path / "boost.dd"
    path.write_bytes(b"boost")
    return EvidenceImage(
        evidence_id="ev-boost-1",
        file_path=path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=5,
        acquired_at=datetime(2024, 1, 1, tzinfo=UTC),
        case=CaseMetadata(case_id=case_id, case_name="Boost", investigator="Lead"),
    )


def _hash_set() -> HashSet:
    return HashSet(
        md5="0" * 32,
        sha1="1" * 40,
        sha256="a" * 64,
        file_size_bytes=5,
    )


# --- base_repo ---


@pytest.mark.asyncio
async def test_base_repo_crud_and_field_helpers(db_engine: DatabaseEngine, seeded_db: dict) -> None:
    repo = SQLAlchemyUserRepository(db_engine.session_factory)
    admin = await repo.get_by_username("admin")
    assert admin is not None
    assert await repo.get(admin.id) is not None
    assert await repo.count() >= 3
    by_field = await repo.get_by_field("username", "admin")
    assert by_field is not None
    listed = await repo.list_by_field("is_active", True)
    assert len(listed) >= 1
    with pytest.raises(DatabaseError, match="Unknown field"):
        await repo.get_by_field("not_a_column", "x")
    with pytest.raises(DatabaseError, match="Unknown field"):
        await repo.list_by_field("not_a_column", "x")


@pytest.mark.asyncio
async def test_base_repo_error_paths() -> None:
    factory = _failing_session()
    repo = SQLAlchemyRepository(
        factory,
        UserORM,
        to_domain=lambda o: o,
        to_orm=lambda e: e,
    )
    with pytest.raises(DatabaseError, match="save"):
        await repo.save(MagicMock())
    with pytest.raises(DatabaseError, match="load"):
        await repo.get("id")
    with pytest.raises(DatabaseError, match="list"):
        await repo.list_all()
    with pytest.raises(DatabaseError, match="delete"):
        await repo.delete("id")
    with pytest.raises(DatabaseError, match="query by field"):
        await repo.get_by_field("username", "x")
    with pytest.raises(DatabaseError, match="list by field"):
        await repo.list_by_field("username", "x")
    with pytest.raises(DatabaseError, match="count"):
        await repo.count()


# --- case_repo ---


@pytest.mark.asyncio
async def test_case_repo_lifecycle_and_investigators(
    db_engine: DatabaseEngine,
    seeded_db: dict,
    tmp_path: Path,
) -> None:
    user_id = seeded_db["user_ids"]["investigator"]
    case_repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    evidence_repo = SQLAlchemyEvidenceRepository(db_engine.session_factory)

    case = _case(user_id)
    await case_repo.save(case, created_by_user_id=user_id)
    loaded = await case_repo.get(case.case_id)
    assert loaded is not None

    opened = await case_repo.update_status(case.case_id, CaseStatus.OPEN)
    assert opened.status is CaseStatus.OPEN
    assert opened.opened_at is not None

    closed = await case_repo.update_status(case.case_id, CaseStatus.CLOSED)
    assert closed.closed_at is not None
    archived = await case_repo.update_status(case.case_id, CaseStatus.ARCHIVED)
    assert archived.archived_at is not None

    member = CaseInvestigator(
        user_id=seeded_db["user_ids"]["analyst"],
        username="analyst",
        full_name="Analyst",
        role="member",
    )
    await case_repo.add_investigator(case.case_id, member)
    by_inv = await case_repo.get_by_investigator(member.user_id)
    assert any(c.case_id == case.case_id for c in by_inv)
    assert await case_repo.remove_investigator(case.case_id, member.user_id) is True
    assert await case_repo.remove_investigator(case.case_id, member.user_id) is False

    evidence = _evidence(tmp_path, case.case_id)
    await evidence_repo.save(evidence)
    await case_repo.add_evidence_id(case.case_id, evidence.evidence_id)

    assert await case_repo.delete("missing") is False
    assert await case_repo.delete(case.case_id) is True


@pytest.mark.asyncio
async def test_case_repo_error_paths() -> None:
    factory = _failing_session()
    repo = SQLAlchemyCaseRepository(factory)
    with pytest.raises(DatabaseError):
        await repo.save(_case("u1"), created_by_user_id="u1")
    with pytest.raises(DatabaseError):
        await repo.get("c1")
    with pytest.raises(DatabaseError):
        await repo.list_all()
    with pytest.raises(DatabaseError):
        await repo.delete("c1")
    with pytest.raises(DatabaseError):
        await repo.get_by_status(CaseStatus.OPEN)
    with pytest.raises(DatabaseError):
        await repo.get_by_investigator("u1")


# --- evidence_status / metadata ---


@pytest.mark.asyncio
async def test_evidence_status_and_metadata_repos(
    db_engine: DatabaseEngine,
    seeded_db: dict,
    tmp_path: Path,
) -> None:
    evidence_repo = SQLAlchemyEvidenceRepository(db_engine.session_factory)
    status_repo = EvidenceStatusRepository(db_engine.session_factory)
    meta_repo = EvidenceMetadataRepository(db_engine.session_factory)
    evidence = _evidence(tmp_path)
    await evidence_repo.save(evidence)

    change = EvidenceStatusChange(
        evidence_id=evidence.evidence_id,
        previous_status=None,
        new_status=EvidenceStatus.REGISTERED,
        changed_by_user_id=seeded_db["user_ids"]["admin"],
        reason="registered",
    )
    await status_repo.add_status_change(change)
    history = await status_repo.get_history(evidence.evidence_id)
    assert history and history[0].new_status is EvidenceStatus.REGISTERED
    assert await status_repo.get_current_status(evidence.evidence_id) is EvidenceStatus.REGISTERED
    ids = await status_repo.get_by_status(EvidenceStatus.REGISTERED)
    assert evidence.evidence_id in ids

    metadata = EvidenceMetadataRecord(
        evidence_id=evidence.evidence_id,
        mime_type="application/octet-stream",
        mime_detected_from="extension",
        file_extension=".dd",
        file_size_bytes=5,
        hash_set=_hash_set(),
        is_valid_format=True,
        validation_notes=["ok"],
    )
    await meta_repo.save_metadata(metadata)
    loaded = await meta_repo.get_metadata(evidence.evidence_id)
    assert loaded is not None
    assert loaded.hash_set.sha256 == "a" * 64
    assert await meta_repo.get_hash_set(evidence.evidence_id) is not None
    by_mime = await meta_repo.get_by_mime_type("application/octet-stream")
    assert any(m.evidence_id == evidence.evidence_id for m in by_mime)
    statuses = await status_repo.get_current_statuses([evidence.evidence_id, "missing"])
    assert statuses[evidence.evidence_id] is EvidenceStatus.REGISTERED
    batched_meta = await meta_repo.get_by_evidence_ids([evidence.evidence_id])
    assert evidence.evidence_id in batched_meta
    batched_evidence = await evidence_repo.get_by_ids([evidence.evidence_id])
    assert evidence.evidence_id in batched_evidence
    # upsert path
    metadata.validation_notes = ["updated"]
    await meta_repo.save_metadata(metadata)


@pytest.mark.asyncio
async def test_evidence_status_error_paths() -> None:
    factory = _failing_session()
    status_repo = EvidenceStatusRepository(factory)
    meta_repo = EvidenceMetadataRepository(factory)
    change = EvidenceStatusChange(
        evidence_id="ev",
        new_status=EvidenceStatus.REGISTERED,
        changed_by_user_id="u",
        reason="r",
    )
    with pytest.raises(DatabaseError):
        await status_repo.add_status_change(change)
    with pytest.raises(DatabaseError):
        await status_repo.get_history("ev")
    with pytest.raises(DatabaseError):
        await status_repo.get_current_status("ev")
    with pytest.raises(DatabaseError):
        await status_repo.get_by_status(EvidenceStatus.REGISTERED)
    with pytest.raises(DatabaseError):
        await status_repo.get_current_statuses(["ev"])
    meta = EvidenceMetadataRecord(
        evidence_id="ev",
        mime_type="x",
        mime_detected_from="x",
        file_extension=".dd",
        file_size_bytes=1,
        hash_set=_hash_set(),
        is_valid_format=True,
        validation_notes=[],
    )
    with pytest.raises(DatabaseError):
        await meta_repo.save_metadata(meta)
    with pytest.raises(DatabaseError):
        await meta_repo.get_metadata("ev")
    with pytest.raises(DatabaseError):
        await meta_repo.get_by_evidence_ids(["ev"])
    with pytest.raises(DatabaseError):
        await meta_repo.get_by_mime_type("x")


# --- user_repo ---


@pytest.mark.asyncio
async def test_user_repo_lockout_helpers(
    db_engine: DatabaseEngine,
    seeded_db: dict,
) -> None:
    repo = SQLAlchemyUserRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["viewer"]
    await repo.increment_failed_attempts(user_id)
    await repo.reset_failed_attempts(user_id)
    until = datetime.now(UTC) + timedelta(hours=1)
    await repo.lock_user(user_id, until)
    await repo.unlock_user(user_id)
    await repo.update_last_login(user_id)
    user = await repo.get(user_id)
    assert user is not None
    assert user.failed_login_attempts == 0
    assert user.is_locked is False
    assert user.last_login is not None


@pytest.mark.asyncio
async def test_user_repo_error_paths() -> None:
    factory = _failing_session()
    repo = SQLAlchemyUserRepository(factory)
    with pytest.raises(DatabaseError):
        await repo.get_by_username("x")
    with pytest.raises(DatabaseError):
        await repo.get_by_email("x")
    with pytest.raises(DatabaseError):
        await repo.get_role_by_name("admin")
    with pytest.raises(DatabaseError):
        await repo.get("u")
    with pytest.raises(DatabaseError):
        await repo.list_all()
    with pytest.raises(DatabaseError):
        await repo.increment_failed_attempts("u")
    with pytest.raises(DatabaseError):
        await repo.reset_failed_attempts("u")
    with pytest.raises(DatabaseError):
        await repo.lock_user("u", datetime.now(UTC))
    with pytest.raises(DatabaseError):
        await repo.unlock_user("u")
    with pytest.raises(DatabaseError):
        await repo.update_last_login("u")


# --- artefact_repo ---


@pytest.mark.asyncio
async def test_artefact_repo_helpers(
    db_engine: DatabaseEngine,
    sample_artefact_set: ArtefactSet,
) -> None:
    repo = SQLAlchemyArtefactRepository(db_engine.session_factory)
    await repo.save(sample_artefact_set)
    loaded = await repo.get(sample_artefact_set.evidence_id)
    assert loaded is not None
    assert loaded.total_count == sample_artefact_set.total_count
    batched = await repo.get_by_evidence_ids([sample_artefact_set.evidence_id])
    assert sample_artefact_set.evidence_id in batched
    listed = await repo.list_all()
    assert any(s.evidence_id == sample_artefact_set.evidence_id for s in listed)
    art = sample_artefact_set.artefacts[0]
    by_id = await repo.get_by_artefact_id(art.artefact_id)
    assert by_id is not None
    by_cat = await repo.get_by_category(
        sample_artefact_set.evidence_id, art.category
    )
    assert by_cat
    assert await repo.count_by_evidence(sample_artefact_set.evidence_id) >= 1
    assert await repo.delete(sample_artefact_set.evidence_id) is True
    assert await repo.get(sample_artefact_set.evidence_id) is None


@pytest.mark.asyncio
async def test_artefact_repo_error_paths() -> None:
    factory = _failing_session()
    repo = SQLAlchemyArtefactRepository(factory)
    aset = ArtefactSet(
        evidence_id="ev",
        artefacts=[
            Artefact(
                category=ArtefactCategory.FILESYSTEM_METADATA,
                source_evidence_id="ev",
                raw_data={},
            )
        ],
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )
    with pytest.raises(DatabaseError):
        await repo.save(aset)
    with pytest.raises(DatabaseError):
        await repo.get("ev")
    with pytest.raises(DatabaseError):
        await repo.get_by_evidence_ids(["ev"])
    with pytest.raises(DatabaseError):
        await repo.list_all()
    with pytest.raises(DatabaseError):
        await repo.delete("ev")
    with pytest.raises(DatabaseError):
        await repo.get_by_artefact_id("a")
    with pytest.raises(DatabaseError):
        await repo.get_by_category("ev", ArtefactCategory.FILESYSTEM_METADATA)
    with pytest.raises(DatabaseError):
        await repo.count_by_evidence("ev")


# --- session_repo ---


@pytest.mark.asyncio
async def test_session_repo_lifecycle(
    db_engine: DatabaseEngine,
    seeded_db: dict,
) -> None:
    repo = SessionRepository(db_engine.session_factory)
    user_id = seeded_db["user_ids"]["admin"]
    jti = str(uuid4())
    expires = datetime.now(UTC) + timedelta(hours=1)
    row = await repo.create_session(user_id, jti, expires, "127.0.0.1", "pytest")
    assert row.token_jti == jti
    assert await repo.get_by_jti(jti) is not None
    assert await repo.is_token_revoked(jti) is False
    assert await repo.revoke_session(jti) is True
    assert await repo.is_token_revoked(jti) is True
    jti2 = str(uuid4())
    await repo.create_session(user_id, jti2, expires, "127.0.0.1", "pytest")
    assert await repo.revoke_all_user_sessions(user_id) >= 1
    # expired + revoked cleanup
    past = datetime.now(UTC) - timedelta(hours=2)
    jti3 = str(uuid4())
    await repo.create_session(user_id, jti3, past, "127.0.0.1", "pytest")
    await repo.revoke_session(jti3)
    assert await repo.cleanup_expired() >= 1
    assert await repo.is_token_revoked("unknown-jti") is False


@pytest.mark.asyncio
async def test_session_repo_error_paths() -> None:
    factory = _failing_session()
    repo = SessionRepository(factory)
    with pytest.raises(DatabaseError):
        await repo.create_session("u", "j", datetime.now(UTC), "ip", "ua")
    with pytest.raises(DatabaseError):
        await repo.get_by_jti("j")
    with pytest.raises(DatabaseError):
        await repo.revoke_session("j")
    with pytest.raises(DatabaseError):
        await repo.revoke_all_user_sessions("u")
    with pytest.raises(DatabaseError):
        await repo.cleanup_expired()


# --- custody / report / evidence / audit / evaluation / ai ---


@pytest.mark.asyncio
async def test_custody_report_evidence_audit_evaluation_ai(
    db_engine: DatabaseEngine,
    seeded_db: dict,
    tmp_path: Path,
    sample_case_metadata: CaseMetadata,
) -> None:
    custody = CustodyRepository(db_engine.session_factory)
    evidence_repo = SQLAlchemyEvidenceRepository(db_engine.session_factory)
    evidence = _evidence(tmp_path)
    await evidence_repo.save(evidence)

    record = ChainOfCustodyRecord(
        evidence_id=evidence.evidence_id,
        action=CustodyAction.ACQUIRED,
        performed_by_user_id=seeded_db["user_ids"]["admin"],
        performed_by_name="Admin",
        reason="acq",
        hash_at_action="a" * 64,
        entry_number=1,
    )
    await custody.add_record(record)
    chain = await custody.get_chain(evidence.evidence_id)
    assert len(chain) == 1
    chains = await custody.get_chains([evidence.evidence_id])
    assert evidence.evidence_id in chains
    assert len(chains[evidence.evidence_id]) == 1
    assert await custody.get_latest(evidence.evidence_id) is not None
    assert await custody.get_by_user(seeded_db["user_ids"]["admin"])
    assert await custody.count_by_evidence(evidence.evidence_id) == 1

    report_repo = SQLAlchemyReportRepository(db_engine.session_factory)
    report = ForensicReport(
        report_id="rep-boost-1",
        case=sample_case_metadata,
        json_report=JSONReport(
            report_id="j1",
            evidence_id=evidence.evidence_id,
            artefact_data=[],
            integrity_hash="b" * 64,
        ),
        narrative_report=NarrativeReport(
            report_id="n1",
            evidence_id=evidence.evidence_id,
            summary_text="s",
            llm_model_used="mock",
        ),
        pipeline_duration_seconds=1.0,
    )
    await report_repo.save(report)
    assert await report_repo.get("rep-boost-1") is not None
    assert await report_repo.get_by_case(sample_case_metadata.case_id)
    assert await report_repo.list_all()
    assert await report_repo.delete("rep-boost-1") is True

    assert await evidence_repo.get(evidence.evidence_id) is not None
    assert await evidence_repo.get_by_case(evidence.case.case_id)
    assert await evidence_repo.get_by_hash("a" * 64) is not None
    assert await evidence_repo.list_all()
    assert await evidence_repo.delete(evidence.evidence_id) is True

    audit = SQLAlchemyAuditRepository(db_engine.session_factory)
    entry = AuditEntry(
        entry_number=1,
        stage=PipelineStage.ACQUISITION,
        action="test",
        evidence_id="ev-x",
        details={},
    )
    await audit.log_entry(entry, user_id=seeded_db["user_ids"]["admin"])
    assert await audit.get_by_evidence("ev-x")
    assert await audit.get_by_user(seeded_db["user_ids"]["admin"])
    assert await audit.get_by_stage(PipelineStage.ACQUISITION)
    assert await audit.get_by_date_range(
        datetime(2020, 1, 1, tzinfo=UTC),
        datetime(2099, 1, 1, tzinfo=UTC),
    )
    assert await audit.get_latest_entry_number() >= 1

    bench = SQLAlchemyBenchmarkRepository(db_engine.session_factory)
    use = SQLAlchemyUsabilityRepository(db_engine.session_factory)
    result = BenchmarkResult(
        benchmark_id="bench-boost",
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
    await bench.save(result)
    assert await bench.get("bench-boost") is not None
    assert await bench.list_all()
    response = UsabilityResponse(
        response_id="use-boost",
        participant_id="p1",
        usefulness_rating=5,
        accuracy_rating=5,
        clarity_rating=4,
    )
    await use.save(response)
    assert await use.get_all_responses()

    ai = SQLAlchemyAIAnalysisRepository(db_engine.session_factory)
    rec = AIAnalysisRecordORM(
        evidence_id="ev-ai",
        analysis_type="classify",
        model_used="mock",
        prompt_version="1.0.0",
        input_artefact_count=1,
        output_token_count=10,
        confidence_score=0.9,
        duration_ms=12.0,
    )
    saved = await ai.save(rec)
    assert saved.id
    assert await ai.get(saved.id) is not None
    assert await ai.get("missing") is None


@pytest.mark.asyncio
async def test_remaining_repo_error_paths() -> None:
    factory = _failing_session()
    custody = CustodyRepository(factory)
    with pytest.raises(DatabaseError):
        await custody.add_record(
            ChainOfCustodyRecord(
                evidence_id="e",
                action=CustodyAction.ACQUIRED,
                performed_by_user_id="u",
                performed_by_name="n",
                reason="r",
                hash_at_action="a" * 64,
                entry_number=1,
            )
        )
    with pytest.raises(DatabaseError):
        await custody.get_chain("e")
    with pytest.raises(DatabaseError):
        await custody.get_chains(["e"])
    with pytest.raises(DatabaseError):
        await custody.get_latest("e")
    with pytest.raises(DatabaseError):
        await custody.get_by_user("u")
    with pytest.raises(DatabaseError):
        await custody.count_by_evidence("e")

    report = SQLAlchemyReportRepository(factory)
    with pytest.raises(DatabaseError):
        await report.get("r")
    with pytest.raises(DatabaseError):
        await report.list_all()

    evidence = SQLAlchemyEvidenceRepository(factory)
    with pytest.raises(DatabaseError):
        await evidence.get("e")
    with pytest.raises(DatabaseError):
        await evidence.list_all()

    audit = SQLAlchemyAuditRepository(factory)
    with pytest.raises(DatabaseError):
        await audit.log_entry(
            AuditEntry(
                entry_number=1,
                stage=PipelineStage.ACQUISITION,
                action="a",
                evidence_id="e",
                details={},
            )
        )
    with pytest.raises(DatabaseError):
        await audit.get_latest_entry_number()
    with pytest.raises(DatabaseError):
        await audit.get_by_evidence("e")

    use = SQLAlchemyUsabilityRepository(factory)
    with pytest.raises(DatabaseError):
        await use.get_all_responses()

    ai = SQLAlchemyAIAnalysisRepository(factory)
    with pytest.raises(DatabaseError):
        await ai.save(
            AIAnalysisRecordORM(
                evidence_id="e",
                analysis_type="t",
                model_used="m",
            )
        )
    with pytest.raises(DatabaseError):
        await ai.get("id")
