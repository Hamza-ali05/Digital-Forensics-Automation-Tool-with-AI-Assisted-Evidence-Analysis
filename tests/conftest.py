"""Shared pytest fixtures for DFAT unit and integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dfat.app import create_app
from dfat.core.enums import ArtefactCategory, EvidenceType, HashAlgorithm, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.infrastructure.storage.local_storage import LocalFileStorage


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
def app_client(tmp_path: Path) -> TestClient:
    """Return a FastAPI TestClient with isolated storage directories."""
    from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
    from dfat.infrastructure.repositories.artefact_repo import JSONArtefactRepository
    from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
    from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
    from dfat.infrastructure.storage.local_storage import LocalFileStorage
    from dfat.infrastructure.storage.secure_storage import SecureStorage
    from dfat.core.enums import HashAlgorithm

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

    container.storage.local_storage.override(local)
    container.storage.secure_storage.override(secure)
    container.logging.forensic_audit_logger.override(audit)
    container.repositories.evidence_repo.override(FileSystemEvidenceRepository(local))
    container.repositories.artefact_repo.override(JSONArtefactRepository(local))
    container.repositories.report_repo.override(FileSystemReportRepository(secure))

    # Rebuild pipeline orchestrator so it uses the isolated repositories.
    container.pipeline.pipeline_orchestrator.reset()

    return TestClient(app)


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the tests/fixtures directory."""
    return Path(__file__).resolve().parent / "fixtures"
