"""Unit tests for SQLAlchemy repositories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, PipelineStage
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.pipeline import AuditEntry
from dfat.database.engine import DatabaseEngine
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository
from dfat.database.repositories.audit_repo import SQLAlchemyAuditRepository
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.database.repositories.session_repo import SessionRepository


def _evidence(evidence_id: str, path: Path) -> EvidenceImage:
    return EvidenceImage(
        evidence_id=evidence_id,
        file_path=path,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash=("a" * 63) + evidence_id[-1],
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=path.stat().st_size,
        acquired_at=datetime(2024, 1, 15, tzinfo=UTC),
        case=CaseMetadata(
            case_id=f"case-{evidence_id}",
            case_name="Repo Case",
            investigator="Tester",
        ),
    )


@pytest.mark.asyncio
async def test_evidence_repo_save_and_get(
    db_engine: DatabaseEngine,
    tmp_path: Path,
) -> None:
    """Save EvidenceImage then load it by ID."""
    # Arrange
    path = tmp_path / "e1.dd"
    path.write_bytes(b"one")
    repo = SQLAlchemyEvidenceRepository(db_engine.session_factory)
    evidence = _evidence("ev-save-1", path)

    # Act
    await repo.save(evidence)
    loaded = await repo.get("ev-save-1")

    # Assert
    assert loaded is not None
    assert loaded.evidence_id == "ev-save-1"
    assert loaded.original_hash == evidence.original_hash


@pytest.mark.asyncio
async def test_evidence_repo_list_all(db_engine: DatabaseEngine, tmp_path: Path) -> None:
    """Saving three evidence records yields three list results."""
    # Arrange
    repo = SQLAlchemyEvidenceRepository(db_engine.session_factory)
    for idx in range(3):
        path = tmp_path / f"e{idx}.dd"
        path.write_bytes(b"x")
        await repo.save(_evidence(f"ev-list-{idx}", path))

    # Act
    items = await repo.list_all()

    # Assert
    assert len(items) >= 3
    assert {item.evidence_id for item in items} >= {
        "ev-list-0",
        "ev-list-1",
        "ev-list-2",
    }


@pytest.mark.asyncio
async def test_evidence_repo_delete(db_engine: DatabaseEngine, tmp_path: Path) -> None:
    """Delete removes evidence metadata while leaving the file intact."""
    # Arrange
    path = tmp_path / "del.dd"
    path.write_bytes(b"del")
    repo = SQLAlchemyEvidenceRepository(db_engine.session_factory)
    await repo.save(_evidence("ev-del-1", path))

    # Act
    deleted = await repo.delete("ev-del-1")
    loaded = await repo.get("ev-del-1")

    # Assert
    assert deleted is True
    assert loaded is None
    assert path.exists()


@pytest.mark.asyncio
async def test_artefact_repo_save_artefact_set(
    db_engine: DatabaseEngine,
    sample_artefact_set: ArtefactSet,
) -> None:
    """Persist an ArtefactSet containing five artefacts."""
    # Arrange
    repo = SQLAlchemyArtefactRepository(db_engine.session_factory)

    # Act
    await repo.save(sample_artefact_set)
    loaded = await repo.get(sample_artefact_set.evidence_id)

    # Assert
    assert loaded is not None
    assert loaded.total_count == 5


@pytest.mark.asyncio
async def test_artefact_repo_get_by_category(
    db_engine: DatabaseEngine,
    sample_artefact_set: ArtefactSet,
) -> None:
    """Filter artefacts by ArtefactCategory."""
    # Arrange
    repo = SQLAlchemyArtefactRepository(db_engine.session_factory)
    await repo.save(sample_artefact_set)

    # Act
    browser = await repo.get_by_category(
        sample_artefact_set.evidence_id,
        ArtefactCategory.BROWSER_HISTORY,
    )

    # Assert
    assert len(browser) == 1
    assert browser[0].category is ArtefactCategory.BROWSER_HISTORY


@pytest.mark.asyncio
async def test_audit_repo_log_and_retrieve(db_engine: DatabaseEngine) -> None:
    """Log three entries and retrieve them by evidence ID."""
    # Arrange
    repo = SQLAlchemyAuditRepository(db_engine.session_factory)
    for number in (1, 2, 3):
        await repo.log_entry(
            AuditEntry(
                entry_number=number,
                stage=PipelineStage.ACQUISITION,
                action=f"ACTION_{number}",
                evidence_id="ev-audit-1",
                details={"n": number},
            ),
            user_id="user-1",
        )

    # Act
    entries = await repo.get_by_evidence("ev-audit-1")

    # Assert
    assert len(entries) == 3
    assert [entry.entry_number for entry in entries] == [1, 2, 3]


@pytest.mark.asyncio
async def test_audit_repo_no_update_or_delete(db_engine: DatabaseEngine) -> None:
    """Audit repository has no update/delete mutators."""
    # Arrange
    repo = SQLAlchemyAuditRepository(db_engine.session_factory)

    # Act / Assert
    assert not hasattr(repo, "update")
    assert not hasattr(repo, "delete")
    with pytest.raises(AttributeError):
        repo.delete("anything")  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_session_repo_create_and_revoke(db_engine: DatabaseEngine) -> None:
    """Create a session, revoke it, and confirm revocation status."""
    # Arrange
    # Session FK requires a user row — insert a minimal role+user.
    from dfat.database.models.user import RoleORM, UserORM

    async with db_engine.session_factory() as session:
        session.add(
            RoleORM(
                id="role-admin",
                name="admin",
                description="admin",
                permissions="{}",
            )
        )
        session.add(
            UserORM(
                id="user-sess-1",
                username="sessuser",
                email="sess@example.com",
                hashed_password="hash",
                full_name="Sess",
                role_id="role-admin",
            )
        )
        await session.commit()

    repo = SessionRepository(db_engine.session_factory)
    jti = "jti-session-1"

    # Act
    await repo.create_session(
        "user-sess-1",
        jti,
        datetime.now(UTC) + timedelta(hours=1),
        "127.0.0.1",
        "pytest",
    )
    assert await repo.is_token_revoked(jti) is False
    revoked = await repo.revoke_session(jti)

    # Assert
    assert revoked is True
    assert await repo.is_token_revoked(jti) is True
