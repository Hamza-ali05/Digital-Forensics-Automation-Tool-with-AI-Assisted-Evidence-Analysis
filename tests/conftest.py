"""Shared pytest fixtures for DFAT unit and integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from dfat.app import create_app
from dfat.auth.jwt_handler import JWTHandler
from dfat.auth.password import PasswordHasher
from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.case import Case, CaseInvestigator
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.case_management.enums import CaseStatus, CustodyAction
from dfat.evidence_management.models import ChainOfCustodyRecord, HashSet
from dfat.database.engine import DatabaseEngine
from dfat.database.models.user import RoleORM, UserORM
from dfat.database.repositories.case_repo import SQLAlchemyCaseRepository
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
TEST_INVESTIGATOR_USERNAME = "investigator"
TEST_INVESTIGATOR_PASSWORD = "InvestPass123!"

SAMPLE_EVIDENCE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_evidence"

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
def mock_llm_response() -> str:
    """Return valid classification JSON for mocked Ollama responses."""
    return (
        '[{"artefact_id":"art-1","suspicion_level":"HIGH",'
        '"reasoning":"RWX region with MZ header",'
        '"ioc_indicators":["MZ header"]}]'
    )


@pytest.fixture
def mock_ollama_client(mock_llm_response: str) -> MagicMock:
    """Return a mocked OllamaClient that never calls a real LLM."""
    client = MagicMock()
    client.generate = AsyncMock(
        return_value=MagicMock(
            text=mock_llm_response,
            model="llama3",
            prompt_tokens=10,
            completion_tokens=5,
        )
    )
    client.chat = AsyncMock(
        return_value=MagicMock(
            text="Artefact art-1 is the primary finding.",
            model="llama3",
            prompt_tokens=10,
            completion_tokens=5,
        )
    )
    client.stream = AsyncMock()
    return client


@pytest.fixture
def mock_artefact_set_for_ai() -> ArtefactSet:
    """Return ~30 artefacts across categories for AI batching tests."""
    evidence_id = "ev-ai-batch-001"
    categories = list(ArtefactCategory)
    artefacts: list[Artefact] = []
    for index in range(30):
        category = categories[index % len(categories)]
        artefacts.append(
            Artefact(
                artefact_id=f"art-ai-{index:03d}",
                category=category,
                source_evidence_id=evidence_id,
                raw_data={
                    "name": f"sample-{index}",
                    "index": index,
                    "category": category.value,
                },
            )
        )
    return ArtefactSet(
        evidence_id=evidence_id,
        artefacts=artefacts,
        categories_present=sorted({item.category for item in artefacts}, key=lambda c: c.value),
    )


@pytest.fixture
def mock_ranked_artefacts(
    mock_artefact_set_for_ai: ArtefactSet,
) -> list[RankedArtefact]:
    """Return ranked artefacts derived from ``mock_artefact_set_for_ai``."""
    levels = [
        SuspicionLevel.CRITICAL,
        SuspicionLevel.HIGH,
        SuspicionLevel.MEDIUM,
        SuspicionLevel.LOW,
        SuspicionLevel.INFORMATIONAL,
    ]
    ranked: list[RankedArtefact] = []
    for index, artefact in enumerate(mock_artefact_set_for_ai.artefacts):
        level = levels[index % len(levels)]
        ranked.append(
            RankedArtefact(
                **artefact.model_dump(),
                suspicion_level=level,
                relevance_score=round(1.0 - (index % 5) * 0.15, 2),
                classification_reasoning=f"Mock ranking for {artefact.artefact_id}",
            )
        )
    return ranked


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
    investigator_id = "user-investigator-00000000-0000-0000-0000-000000000004"
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
        session.add(
            UserORM(
                id=investigator_id,
                username=TEST_INVESTIGATOR_USERNAME,
                email="investigator@example.com",
                hashed_password=hasher.hash_password(TEST_INVESTIGATOR_PASSWORD),
                full_name="Test Investigator",
                role_id="role-investigator",
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
            "investigator": investigator_id,
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
            "investigator": (TEST_INVESTIGATOR_USERNAME, TEST_INVESTIGATOR_PASSWORD),
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
    client.investigator_token = _make_token(jwt_handler, seeded_db, "investigator")  # type: ignore[attr-defined]
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


# ---------------------------------------------------------------------------
# Prompt 3 fixtures — case / evidence management
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_case(sample_case_metadata: CaseMetadata) -> Case:
    """Return a deterministic Case wrapping CaseMetadata."""
    return Case(
        metadata=sample_case_metadata,
        status=CaseStatus.CREATED,
        investigators=[],
        lead_investigator_id=None,
        evidence_ids=[],
        notes=[],
        tags=["fixture"],
    )


@pytest.fixture
def sample_hash_set() -> HashSet:
    """Return a deterministic multi-algorithm hash set."""
    return HashSet(
        md5="0" * 32,
        sha1="1" * 40,
        sha256="a" * 64,
        computed_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        file_size_bytes=1024,
    )


@pytest.fixture
def sample_custody_record(sample_hash_set: HashSet) -> ChainOfCustodyRecord:
    """Return a deterministic ACQUIRED custody record."""
    return ChainOfCustodyRecord(
        record_id="custody-00000000-0000-0000-0000-000000000001",
        evidence_id="ev-00000000-0000-0000-0000-000000000001",
        action=CustodyAction.ACQUIRED,
        performed_by_user_id="user-investigator-00000000-0000-0000-0000-000000000004",
        performed_by_name="Test Investigator",
        timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        reason="Initial acquisition",
        hash_at_action=sample_hash_set.sha256,
        entry_number=1,
    )


@pytest.fixture
def temp_evidence_file(tmp_path: Path) -> Path:
    """Create a deterministic 1 KiB temporary evidence file."""
    path = tmp_path / "temp_evidence.dd"
    path.write_bytes(b"\x00" * 1024)
    return path


@pytest.fixture
async def seeded_case_db(
    db_engine: DatabaseEngine,
    seeded_db: dict[str, Any],
    sample_case_metadata: CaseMetadata,
) -> dict[str, Any]:
    """Seed a case with a lead investigator into the test database."""
    case_repo = SQLAlchemyCaseRepository(db_engine.session_factory)
    investigator_id = seeded_db["user_ids"]["investigator"]
    case = Case(
        metadata=CaseMetadata(
            case_id=sample_case_metadata.case_id,
            case_name=sample_case_metadata.case_name,
            investigator="Test Investigator",
            created_at=sample_case_metadata.created_at,
            description=sample_case_metadata.description,
        ),
        status=CaseStatus.CREATED,
        lead_investigator_id=investigator_id,
        investigators=[
            CaseInvestigator(
                user_id=investigator_id,
                username=TEST_INVESTIGATOR_USERNAME,
                full_name="Test Investigator",
                role="lead",
                assigned_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            )
        ],
    )
    await case_repo.save(case, created_by_user_id=investigator_id)
    loaded = await case_repo.get(case.case_id)
    assert loaded is not None
    return {
        **seeded_db,
        "case_id": loaded.case_id,
        "case": loaded,
    }


# ---------------------------------------------------------------------------
# Prompt 4 fixtures — parsers, pipeline context, volatility
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_artefact_set() -> ArtefactSet:
    """Return 50 artefacts evenly spanning all 7 ArtefactCategory values."""
    evidence_id = "ev-mock-artefact-set-0001"
    categories = list(ArtefactCategory)
    artefacts: list[Artefact] = []
    for index in range(50):
        category = categories[index % len(categories)]
        artefacts.append(
            Artefact(
                artefact_id=f"art-mock-{index:03d}",
                category=category,
                source_evidence_id=evidence_id,
                raw_data=_synthetic_raw_data(category, index),
                metadata={"fixture": "mock_artefact_set", "index": index},
            )
        )
    present = sorted({item.category for item in artefacts}, key=lambda c: c.value)
    return ArtefactSet(
        evidence_id=evidence_id,
        artefacts=artefacts,
        categories_present=present,
    )


def _synthetic_raw_data(category: ArtefactCategory, index: int) -> dict[str, Any]:
    """Build minimal category-valid raw_data for fixture artefacts."""
    if category is ArtefactCategory.FILESYSTEM_METADATA:
        return {
            "filename": f"file{index}.dat",
            "path": f"/path/file{index}.dat",
            "size": index,
            "is_deleted": False,
            "file_type": "file",
        }
    if category is ArtefactCategory.REGISTRY_KEY:
        return {
            "hive_name": "SOFTWARE",
            "key_path": rf"Key\Value{index}",
            "value_name": f"v{index}",
            "value_data": f"data{index}",
            "value_type": "RegSZ",
        }
    if category is ArtefactCategory.BROWSER_HISTORY:
        return {
            "url": f"https://example.com/{index}",
            "title": f"Page {index}",
            "visit_count": index + 1,
            "browser_type": "chrome",
        }
    if category is ArtefactCategory.EVENT_LOG:
        return {
            "event_id": 4624 + (index % 10),
            "message": f"event {index}",
            "is_security_relevant": index % 2 == 0,
        }
    if category is ArtefactCategory.RUNNING_PROCESS:
        return {"pid": 1000 + index, "name": f"proc{index}.exe"}
    if category is ArtefactCategory.NETWORK_CONNECTION:
        return {
            "protocol": "TCP",
            "local_address": "10.0.0.1",
            "remote_address": "8.8.8.8",
            "is_external": True,
            "pid": 1000 + index,
        }
    return {
        "pid": 2000 + index,
        "process_name": f"inj{index}.exe",
        "vad_start": hex(index),
        "protection": "PAGE_EXECUTE_READWRITE",
        "suspicious_indicators": ["MZ header"] if index % 2 == 0 else [],
    }


@pytest.fixture
def mock_parser_registry(mock_artefact_set: ArtefactSet) -> Any:
    """Return a ParserRegistry populated with synthetic stub parsers."""
    from dfat.core.interfaces.parser import IArtefactParser
    from dfat.pipeline.parser_registry import ParserRegistry

    class _SyntheticParser(IArtefactParser):
        def __init__(self, name: str, category: ArtefactCategory) -> None:
            self._name = name
            self._category = category

        @property
        def parser_name(self) -> str:
            return self._name

        def supported_categories(self) -> list[ArtefactCategory]:
            return [self._category]

        def supported_evidence_types(self) -> list[EvidenceType]:
            if self._category in {
                ArtefactCategory.RUNNING_PROCESS,
                ArtefactCategory.NETWORK_CONNECTION,
                ArtefactCategory.INJECTED_CODE,
            }:
                return [EvidenceType.MEMORY_DUMP]
            return [EvidenceType.DISK_IMAGE]

        def parse(self, evidence: EvidenceImage) -> ArtefactSet:
            subset = [
                item
                for item in mock_artefact_set.artefacts
                if item.category is self._category
            ][:3]
            return ArtefactSet(
                evidence_id=evidence.evidence_id,
                artefacts=subset,
                categories_present=[self._category] if subset else [],
            )

        def is_available(self) -> bool:
            return True

    registry = ParserRegistry()
    mapping = [
        ("FileSystemParser", ArtefactCategory.FILESYSTEM_METADATA),
        ("RegistryParser", ArtefactCategory.REGISTRY_KEY),
        ("BrowserHistoryParser", ArtefactCategory.BROWSER_HISTORY),
        ("EventLogParser", ArtefactCategory.EVENT_LOG),
        ("ProcessListParser", ArtefactCategory.RUNNING_PROCESS),
        ("NetworkArtefactParser", ArtefactCategory.NETWORK_CONNECTION),
        ("CodeInjectionParser", ArtefactCategory.INJECTED_CODE),
    ]
    for name, category in mapping:
        registry.register(_SyntheticParser(name, category))
    return registry


@pytest.fixture
def mock_pipeline_context(
    sample_evidence_image: EvidenceImage,
    mock_artefact_set: ArtefactSet,
) -> Any:
    """Return a PipelineContext seeded with job, evidence, and artefacts."""
    from dfat.pipeline.models import PipelineJob
    from dfat.pipeline.stage_interface import PipelineContext

    job = PipelineJob(
        evidence_id=sample_evidence_image.evidence_id,
        case_id=sample_evidence_image.case.case_id,
        user_id="user-fixture-1",
        mode="full",
    )
    return PipelineContext(
        job=job,
        evidence=sample_evidence_image,
        artefact_set=mock_artefact_set,
        metadata={
            "case": sample_evidence_image.case,
            "case_id": sample_evidence_image.case.case_id,
        },
    )


@pytest.fixture
def mock_volatility_runner(mock_audit_logger: MagicMock) -> MagicMock:
    """Return a mocked VolatilityRunner that never touches volatility3."""
    runner = MagicMock()
    runner.is_available.return_value = True
    runner.run_plugin.return_value = [
        {"PID": 4, "PPID": 0, "ImageFileName": "System"},
        {"PID": 100, "PPID": 4, "ImageFileName": "svchost.exe"},
    ]
    runner._audit_logger = mock_audit_logger
    return runner
