"""Query performance tests for indexed repository access patterns.

These tests seed large datasets and assert list/filter queries complete within
budget. They are marked ``performance`` and skipped in default pytest runs.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, PipelineStage
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.database.engine import DatabaseEngine
from dfat.database.models.artefact_orm import ArtefactRecordORM
from dfat.database.models.audit_orm import AuditLogRecordORM
from dfat.database.models.case_orm import CaseORM
from dfat.database.models.evidence_orm import EvidenceRecordORM
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository


def _elapsed_ms(started: float) -> float:
    """Return milliseconds elapsed since ``started`` (perf_counter value)."""
    return (time.perf_counter() - started) * 1000.0


@pytest.mark.performance
async def test_case_list_with_1000_cases(
    db_engine: DatabaseEngine,
    seeded_db: dict[str, Any],
) -> None:
    """Listing 1000 cases (with batched investigator/evidence loads) is < 200ms."""
    user_id = seeded_db["user_ids"]["investigator"]
    now = datetime.now(UTC)
    async with db_engine.session_factory() as session:
        session.add_all(
            [
                CaseORM(
                    id=f"case-perf-{index:04d}",
                    case_name=f"Performance Case {index}",
                    description="seed",
                    status="created",
                    created_by_user_id=user_id,
                    notes="[]",
                    tags="[]",
                    created_at=now,
                    updated_at=now,
                )
                for index in range(1000)
            ]
        )
        await session.commit()

    repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    await repo.list_all()  # warmup (query compile / cache)

    started = time.perf_counter()
    cases = await repo.list_all()
    elapsed = _elapsed_ms(started)

    assert len(cases) >= 1000
    assert elapsed < 200, f"case list took {elapsed:.1f}ms (budget 200ms)"


@pytest.mark.performance
async def test_artefact_query_with_10000_artefacts(
    db_engine: DatabaseEngine,
    tmp_path: Path,
) -> None:
    """Loading 10k artefacts for one evidence item is < 500ms."""
    evidence_id = "ev-perf-artefacts"
    file_path = tmp_path / "perf.dd"
    file_path.write_bytes(b"perf")
    evidence_repo = SQLAlchemyEvidenceRepository(db_engine.session_factory)
    await evidence_repo.save(
        EvidenceImage(
            evidence_id=evidence_id,
            file_path=file_path,
            evidence_type=EvidenceType.DISK_IMAGE,
            original_hash="a" * 64,
            hash_algorithm=HashAlgorithm.SHA256,
            file_size_bytes=4,
            case=CaseMetadata(
                case_id="case-perf-artefacts",
                case_name="Artefact Perf",
                investigator="Tester",
            ),
        )
    )

    now = datetime.now(UTC)
    async with db_engine.session_factory() as session:
        session.add_all(
            [
                ArtefactRecordORM(
                    id=f"art-perf-{index:05d}",
                    evidence_id=evidence_id,
                    category=ArtefactCategory.FILESYSTEM_METADATA.value,
                    source_path=f"/dir/file-{index}",
                    raw_data="{}",
                    parsed_at=now,
                    suspicion_level="high" if index % 10 == 0 else None,
                    metadata_json="{}",
                    created_at=now,
                    updated_at=now,
                )
                for index in range(10_000)
            ]
        )
        await session.commit()

    artefact_repo = SQLAlchemyArtefactRepository(db_engine.session_factory)
    loaded = await artefact_repo.get(evidence_id)
    assert loaded is not None
    assert loaded.total_count == 10_000

    async with db_engine.session_factory() as session:
        started = time.perf_counter()
        result = await session.execute(
            select(ArtefactRecordORM).where(
                ArtefactRecordORM.evidence_id == evidence_id
            )
        )
        rows = result.scalars().all()
        elapsed = _elapsed_ms(started)

    assert len(rows) == 10_000
    assert elapsed < 500, f"artefact query took {elapsed:.1f}ms (budget 500ms)"


@pytest.mark.performance
async def test_audit_trail_query_performance(db_engine: DatabaseEngine) -> None:
    """Querying 5000 audit rows by evidence_id is < 100ms."""
    evidence_id = "ev-perf-audit"
    now = datetime.now(UTC)
    async with db_engine.session_factory() as session:
        session.add(
            EvidenceRecordORM(
                id=evidence_id,
                case_id="case-perf-audit",
                case_name="Audit Perf",
                investigator="Tester",
                file_path="/tmp/audit.dd",
                evidence_type=EvidenceType.DISK_IMAGE.value,
                original_hash="b" * 64,
                hash_algorithm=HashAlgorithm.SHA256.value,
                file_size_bytes=1,
                status="registered",
                created_at=now,
                updated_at=now,
            )
        )
        session.add_all(
            [
                AuditLogRecordORM(
                    id=str(uuid4()),
                    entry_number=index + 1,
                    timestamp=now,
                    stage=PipelineStage.ACQUISITION.value,
                    action="performance seed",
                    evidence_id=evidence_id,
                    details="{}",
                )
                for index in range(5000)
            ]
        )
        await session.commit()

    repo = SQLAlchemyAuditRepository(db_engine.session_factory)
    entries = await repo.get_by_evidence(evidence_id)
    assert len(entries) == 5000

    stmt = (
        select(AuditLogRecordORM.timestamp)
        .where(AuditLogRecordORM.evidence_id == evidence_id)
        .order_by(AuditLogRecordORM.timestamp)
    )
    async with db_engine.session_factory() as session:
        await session.execute(stmt)

    async with db_engine.session_factory() as session:
        started = time.perf_counter()
        result = await session.execute(stmt)
        rows = result.all()
        elapsed = _elapsed_ms(started)

    assert len(rows) == 5000
    assert elapsed < 100, f"audit trail query took {elapsed:.1f}ms (budget 100ms)"
