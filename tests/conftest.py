"""Shared pytest fixtures for DFAT unit and integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from dfat.app import create_app
from dfat.auth.jwt_handler import JWTHandler
from dfat.auth.password import PasswordHasher
from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.database.engine import DatabaseEngine
from dfat.database.models.user import RoleORM, UserORM
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.infrastructure.storage.local_storage import LocalFileStorage
from dfat.settings import AuthSettings

TEST_JWT_SECRET = "test-secret-key-not-for-production"
TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "AdminPass123!"
TEST_ANALYST_USERNAME = "analyst"
TEST_ANALYST_PASSWORD = "AnalystPass12!"
TEST_VIEWER_USERNAME = "viewer"
TEST_VIEWER_PASSWORD = "ViewerPass123!"

_ROLE_SEEDS: list[dict[str, Any]] = [
    {
        "id": "role-admin",
        "name": "admin",
        "description": "Full system administrator",
        "permissions": '{"all": true}',
    },
    {
        "id": "role-investigator",
        "name": "investigator",
        "description": "Lead forensic investigator",
        "permissions": "{}",
    },
    {
        "id": "role-analyst",
        "name": "analyst",
        "description": "Forensic analyst",
        "permissions": "{}",
    },
    {
        "id": "role-viewer",
        "name": "viewer",
        "description": "Read-only viewer",
        "permissions": "{}",
    },
]


@pytest.fixture
def sample_case_metadata() -> CaseMetadata:
    """Return fixed, deterministic case metadata."""
    return CaseMetadata(
        case_id="case-00000000-0000-0000-0000-000000000001",
        case_name="DFAT Sample Case",
        investigator="Investigator Alice",
        created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        description="Deterministic fixture case",
    )


@pytest.fixture
def sample_evidence_image(tmp_path: Path, sample_case_metadata: CaseMetadata) -> EvidenceImage:
    """Create a tiny temp file and wrap it as EvidenceImage metadata."""
    evidence_file = tmp_path / "sample.dd"
    evidence_file.write_bytes(b"DFAT-FAKE-EVIDENCE")
    return EvidenceImage(
        evidence_id="ev-00000000-0000-0000-0000-000000000001",
        file_path=evidence_file,
        evidence_type=EvidenceType.DISK_IMAGE,
        original_hash="a" * 64,
        hash_algorithm=HashAlgorithm.SHA256,
        file_size_bytes=evidence_file.stat().st_size,
        acquired_at=datetime(2024, 1, 15, 12, 5, 0, tzinfo=UTC),
        case=sample_case_metadata,
    )


@pytest.fixture
def sample_artefact_set() -> ArtefactSet:
    """Return an ArtefactSet with one artefact per primary category."""
    evidence_id = "ev-00000000-0000-0000-0000-000000000001"
    parsed_at = datetime(2024, 1, 15, 12, 10, 0, tzinfo=UTC)
    artefacts = [
        Artefact(
            artefact_id="art-fs-001",
            category=ArtefactCategory.FILESYSTEM_METADATA,
            source_evidence_id=evidence_id,
            raw_data={"path": "/Windows/System32/evil.dll", "identifier": "/windows/system32/evil.dll"},
            parsed_at=parsed_at,
            source_path="/Windows/System32/evil.dll",
        ),
        Artefact(
            artefact_id="art-reg-001",
            category=ArtefactCategory.REGISTRY_KEY,
            source_evidence_id=evidence_id,
            raw_data={
                "key_path": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Malware",
                "identifier": "hkcu/software/microsoft/windows/currentversion/run/malware",
            },
            parsed_at=parsed_at,
            source_path="HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Malware",
        ),
        Artefact(
            artefact_id="art-browser-001",
            category=ArtefactCategory.BROWSER_HISTORY,
            source_evidence_id=evidence_id,
            raw_data={
                "url": "http://malicious.example/payload",
                "identifier": "http://malicious.example/payload",
            },
            parsed_at=parsed_at,
            source_path="Chrome/History",
        ),
        Artefact(
            artefact_id="art-event-001",
            category=ArtefactCategory.EVENT_LOG,
            source_evidence_id=evidence_id,
            raw_data={"event_id": 4624, "identifier": "4624"},
            parsed_at=parsed_at,
            source_path="Security.evtx",
        ),
        Artefact(
            artefact_id="art-proc-001",
            category=ArtefactCategory.RUNNING_PROCESS,
            source_evidence_id=evidence_id,
            raw_data={"name": "mimikatz.exe", "pid": 1337, "identifier": "mimikatz.exe"},
            parsed_at=parsed_at,
            source_path="pslist",
        ),
    ]
    return ArtefactSet(
        evidence_id=evidence_id,
        artefacts=artefacts,
        categories_present=[a.category for a in artefacts],
        extraction_timestamp=parsed_at,
    )


@pytest.fixture
def sample_ranked_artefacts(sample_artefact_set: ArtefactSet) -> list[RankedArtefact]:
    """Return ranked artefacts derived from the sample artefact set."""
    levels = [
        SuspicionLevel.HIGH,
        SuspicionLevel.CRITICAL,
        SuspicionLevel.HIGH,
        SuspicionLevel.MEDIUM,
        SuspicionLevel.CRITICAL,
    ]
    scores = [0.8, 1.0, 0.75, 0.5, 0.95]
    ranked: list[RankedArtefact] = []
    for artefact, level, score in zip(sample_artefact_set.artefacts, levels, scores, strict=True):
        ranked.append(
            RankedArtefact(
                **artefact.model_dump(),
                suspicion_level=level,
                relevance_score=score,
                classification_reasoning="Fixture ranking",
            )
        )
    return ranked


@pytest.fixture
def mock_audit_logger() -> MagicMock:
    """Return a mock ForensicAuditLogger."""
    logger = MagicMock(spec=ForensicAuditLogger)
    logger.log_action.return_value = MagicMock()
    return logger


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Return a mock LocalLLMClient with predetermined responses."""
    client = MagicMock()
    client.analyzer_name = "MockLLM"
    client.is_available.return_value = True
    client.analyze.return_value = []
    client.summarize.return_value = "Mock investigative summary."
    return client


@pytest.fixture
def mock_storage(tmp_path: Path) -> LocalFileStorage:
    """Return LocalFileStorage rooted at a temporary directory."""
    return LocalFileStorage(base_dir=tmp_path)


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the tests/fixtures directory."""
    return Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Prompt 2 fixtures — database, auth, and API client
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_engine() -> AsyncIterator[DatabaseEngine]:
    """Create an isolated in-memory SQLite engine for one test."""
    import dfat.database  # noqa: F401 — register ORM metadata

    engine = DatabaseEngine(
        database_url="sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    await engine.create_tables()
    try:
        yield engine
    finally:
        try:
            await engine.drop_tables()
        except Exception:  # noqa: BLE001 — engine may already be disposed
            pass
        try:
            await engine.dispose()
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture
async def db_session(db_engine: DatabaseEngine) -> AsyncIterator[AsyncSession]:
    """Yield a database session that rolls back on cleanup."""
    session = db_engine.session_factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest.fixture
async def seeded_db(db_engine: DatabaseEngine) -> dict[str, Any]:
    """Seed default roles plus admin, analyst, and viewer test users."""
    hasher = PasswordHasher()
    admin_id = "user-admin-00000000-0000-0000-0000-000000000001"
    analyst_id = "user-analyst-00000000-0000-0000-0000-000000000002"
    viewer_id = "user-viewer-00000000-0000-0000-0000-000000000003"
    now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

    async with db_engine.session_factory() as session:
        for seed in _ROLE_SEEDS:
            session.add(
                RoleORM(
                    id=str(seed["id"]),
                    name=str(seed["name"]),
                    description=str(seed["description"]),
                    permissions=str(seed["permissions"]),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            UserORM(
                id=admin_id,
                username=TEST_ADMIN_USERNAME,
                email="admin@example.com",
                hashed_password=hasher.hash_password(TEST_ADMIN_PASSWORD),
                full_name="Test Admin",
                role_id="role-admin",
                is_active=True,
                is_locked=False,
                failed_login_attempts=0,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            UserORM(
                id=analyst_id,
                username=TEST_ANALYST_USERNAME,
                email="analyst@example.com",
                hashed_password=hasher.hash_password(TEST_ANALYST_PASSWORD),
                full_name="Test Analyst",
                role_id="role-analyst",
                is_active=True,
                is_locked=False,
                failed_login_attempts=0,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            UserORM(
                id=viewer_id,
                username=TEST_VIEWER_USERNAME,
                email="viewer@example.com",
                hashed_password=hasher.hash_password(TEST_VIEWER_PASSWORD),
                full_name="Test Viewer",
                role_id="role-viewer",
                is_active=True,
                is_locked=False,
                failed_login_attempts=0,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    return {
        "user_ids": {
            "admin": admin_id,
            "analyst": analyst_id,
            "viewer": viewer_id,
        },
        "role_ids": {
            "admin": "role-admin",
            "investigator": "role-investigator",
            "analyst": "role-analyst",
            "viewer": "role-viewer",
        },
        "credentials": {
            "admin": (TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD),
            "analyst": (TEST_ANALYST_USERNAME, TEST_ANALYST_PASSWORD),
            "viewer": (TEST_VIEWER_USERNAME, TEST_VIEWER_PASSWORD),
        },
    }


@pytest.fixture
def password_hasher() -> PasswordHasher:
    """Return a PasswordHasher instance."""
    return PasswordHasher()


@pytest.fixture
def jwt_handler() -> JWTHandler:
    """Return a JWTHandler configured with the test secret key."""
    return JWTHandler(
        secret_key=TEST_JWT_SECRET,
        algorithm="HS256",
        access_token_expire_minutes=60,
        refresh_token_expire_days=7,
    )


@pytest.fixture
def auth_settings() -> AuthSettings:
    """Return deterministic auth settings for service unit tests."""
    return AuthSettings(
        secret_key=TEST_JWT_SECRET,
        max_login_attempts=5,
        lockout_duration_minutes=30,
        password_min_length=12,
    )


def _make_token(
    jwt_handler: JWTHandler,
    seeded_db: dict[str, Any],
    role: str,
) -> str:
    """Create a non-expired access token for a seeded user role."""
    user_id = seeded_db["user_ids"][role]
    username = seeded_db["credentials"][role][0]
    access, _refresh, _jti = jwt_handler.create_token_pair(user_id, username, role)
    return access


@pytest.fixture
def test_admin_token(jwt_handler: JWTHandler, seeded_db: dict[str, Any]) -> str:
    """Return a valid admin access JWT."""
    return _make_token(jwt_handler, seeded_db, "admin")


@pytest.fixture
def test_analyst_token(jwt_handler: JWTHandler, seeded_db: dict[str, Any]) -> str:
    """Return a valid analyst access JWT."""
    return _make_token(jwt_handler, seeded_db, "analyst")


@pytest.fixture
def test_viewer_token(jwt_handler: JWTHandler, seeded_db: dict[str, Any]) -> str:
    """Return a valid viewer access JWT."""
    return _make_token(jwt_handler, seeded_db, "viewer")


@pytest.fixture
async def app_client(
    db_engine: DatabaseEngine,
    seeded_db: dict[str, Any],
    jwt_handler: JWTHandler,
    tmp_path: Path,
) -> AsyncIterator[TestClient]:
    """Return a TestClient wired to the isolated test database and auth."""
    from dfat.core.enums import HashAlgorithm
    from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
    from dfat.infrastructure.repositories.artefact_repo import JSONArtefactRepository
    from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
    from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
    from dfat.infrastructure.storage.local_storage import LocalFileStorage
    from dfat.infrastructure.storage.secure_storage import SecureStorage

    evidence_dir = tmp_path / "evidence"
    reports_dir = tmp_path / "reports"
    audit_path = tmp_path / "audit.jsonl"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    app = create_app()
    container = app.state.container

    local = LocalFileStorage(evidence_dir)
    secure = SecureStorage(reports_dir)
    audit = ForensicAuditLogger(audit_path, HashAlgorithm.SHA256)

    container.database.database_engine.override(db_engine)
    container.auth.jwt_handler.override(jwt_handler)
    container.auth.password_hasher.override(PasswordHasher())
    container.storage.local_storage.override(local)
    container.storage.secure_storage.override(secure)
    container.logging.forensic_audit_logger.override(audit)
    container.repositories.file_evidence_repo.override(FileSystemEvidenceRepository(local))
    container.repositories.file_artefact_repo.override(JSONArtefactRepository(local))
    container.repositories.file_report_repo.override(FileSystemReportRepository(secure))
    container.pipeline.pipeline_orchestrator.reset()

    client = TestClient(app)
    # Convenience attributes for Prompt 1 route tests (auth required).
    client.admin_token = _make_token(jwt_handler, seeded_db, "admin")  # type: ignore[attr-defined]
    client.analyst_token = _make_token(jwt_handler, seeded_db, "analyst")  # type: ignore[attr-defined]
    client.viewer_token = _make_token(jwt_handler, seeded_db, "viewer")  # type: ignore[attr-defined]
    client.seeded_db = seeded_db  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        container.database.database_engine.reset_override()
        container.auth.jwt_handler.reset_override()
        container.auth.password_hasher.reset_override()
        container.storage.local_storage.reset_override()
        container.storage.secure_storage.reset_override()
        container.logging.forensic_audit_logger.reset_override()
        container.repositories.file_evidence_repo.reset_override()
        container.repositories.file_artefact_repo.reset_override()
        container.repositories.file_report_repo.reset_override()
