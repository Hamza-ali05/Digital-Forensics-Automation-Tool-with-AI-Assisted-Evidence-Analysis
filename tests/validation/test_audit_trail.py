"""Validation tests for the forensic audit trail (Prompt 9.12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from dfat.core.enums import PipelineStage
from dfat.core.models.pipeline import StageResult
from dfat.database.models.audit_orm import AuditLogRecordORM
from dfat.pipeline.job_manager import JobManager
from dfat.pipeline.job_runner import JobRunner
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.pipeline.stage_registry import StageRegistry
from tests.conftest import (
    SAMPLE_EVIDENCE_DIR,
    TEST_INVESTIGATOR_PASSWORD,
    TEST_INVESTIGATOR_USERNAME,
)

_SIGNIFICANT_ACTIONS = frozenset(
    {
        "USER_AUTHENTICATED",
        "case_created",
        "evidence_register_and_validate",
        "PIPELINE_JOB_STARTED",
        "PIPELINE_STAGE_COMPLETED",
        "PIPELINE_JOB_COMPLETED",
    }
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _open_active_case(
    client: TestClient, headers: dict[str, str], seeded_db: dict[str, Any]
) -> str:
    created = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "Audit Trail Validation", "description": "prompt-9.12"},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    assert (
        client.post(
            f"/api/v1/cases/{case_id}/investigators",
            headers=headers,
            json={"user_id": seeded_db["user_ids"]["investigator"], "role": "lead"},
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/cases/{case_id}/open", headers=headers).status_code == 200
    assert (
        client.post(f"/api/v1/cases/{case_id}/activate", headers=headers).status_code
        == 200
    )
    return case_id


def _register_evidence(
    client: TestClient,
    headers: dict[str, str],
    *,
    case_id: str,
    tmp_path: Path,
) -> str:
    path = tmp_path / f"audit-{uuid4().hex[:8]}.dd"
    path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": "audit-trail-validation",
        },
    )
    assert registered.status_code == 201, registered.text
    return str(registered.json()["evidence_id"])


async def _audit_rows(client: TestClient) -> list[AuditLogRecordORM]:
    engine = client.app.state.container.database.database_engine()
    async with engine.session_factory() as session:
        result = await session.execute(
            select(AuditLogRecordORM).order_by(AuditLogRecordORM.entry_number)
        )
        return list(result.scalars().all())


def _file_audit_entries(client: TestClient) -> list[dict[str, Any]]:
    audit_logger = client.app.state.container.logging.forensic_audit_logger()
    path = Path(audit_logger._audit_log_path)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        loaded = json.loads(stripped)
        entry = loaded.get("entry", loaded)
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


class _FakeStage(IPipelineStage):
    """No-op stage used to generate one audit entry per pipeline stage."""

    def __init__(self, stage: PipelineStage) -> None:
        self._stage = stage

    @property
    def stage_name(self) -> PipelineStage:
        return self._stage

    @property
    def description(self) -> str:
        return f"Fake {self._stage.value} stage"

    async def validate_preconditions(self, context: PipelineContext) -> bool:
        return True

    async def execute(self, context: PipelineContext) -> StageResult:
        return StageResult(
            stage=self._stage,
            success=True,
            duration_seconds=0.001,
            output_data={"stage": self._stage.value},
        )


async def _run_audited_pipeline(
    client: TestClient,
    *,
    evidence_id: str,
    case_id: str,
    user_id: str,
) -> str:
    audit_service = client.app.state.container.services.audit_service()
    registry = StageRegistry()
    for stage in PipelineStage:
        registry.register(_FakeStage(stage))
    manager = JobManager(audit_service=audit_service, max_concurrent=1)
    runner = JobRunner(manager, registry, audit_service)
    job = await manager.submit_job(
        evidence_id=evidence_id,
        case_id=case_id,
        user_id=user_id,
        mode="full",
    )
    completed = await runner.run_job(job, PipelineContext(job=job))
    assert completed.status.value == "completed"
    return job.job_id


async def test_login_creates_audit_entry(app_client: TestClient) -> None:
    """Successful login writes a USER_AUTHENTICATED database audit row."""
    # Arrange / Act
    response = app_client.post(
        "/api/v1/auth/login",
        data={
            "username": TEST_INVESTIGATOR_USERNAME,
            "password": TEST_INVESTIGATOR_PASSWORD,
        },
    )

    # Assert
    assert response.status_code == 200, response.text
    user_id = app_client.seeded_db["user_ids"]["investigator"]  # type: ignore[attr-defined]
    matches = [
        row for row in await _audit_rows(app_client) if row.action == "USER_AUTHENTICATED"
    ]
    assert matches, "login should create a USER_AUTHENTICATED audit entry"
    entry = matches[-1]
    assert entry.user_id == user_id
    assert entry.evidence_id == "auth"
    assert entry.timestamp is not None
    assert entry.stage
    assert entry.action == "USER_AUTHENTICATED"


async def test_case_creation_creates_audit_entry(
    app_client: TestClient,
    seeded_db: dict[str, Any],
) -> None:
    """Creating a case writes a case_created audit entry for the actor."""
    # Arrange
    headers = _auth(app_client.investigator_token)  # type: ignore[attr-defined]

    # Act
    created = app_client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "Case Audit", "description": "prompt-9.12"},
    )

    # Assert
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    matches = [
        row
        for row in await _audit_rows(app_client)
        if row.action == "case_created" and row.evidence_id == f"case:{case_id}"
    ]
    assert matches, "case creation should create a case_created audit entry"
    entry = matches[-1]
    assert entry.user_id == seeded_db["user_ids"]["investigator"]
    assert entry.timestamp is not None
    assert entry.stage
    assert entry.action == "case_created"


async def test_evidence_registration_creates_audit_entries(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Register plus integrity verification produce multiple audit steps."""
    # Arrange
    headers = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _open_active_case(app_client, headers, seeded_db)

    # Act
    evidence_id = _register_evidence(
        app_client, headers, case_id=case_id, tmp_path=tmp_path
    )
    verified = app_client.post(
        f"/api/v1/evidence/{evidence_id}/verify-integrity", headers=headers
    )

    # Assert
    assert verified.status_code == 200, verified.text
    db_actions = {
        row.action for row in await _audit_rows(app_client) if row.evidence_id == evidence_id
    }
    file_actions = {
        entry.get("action")
        for entry in _file_audit_entries(app_client)
        if entry.get("evidence_id") == evidence_id
    }
    combined = db_actions | file_actions
    assert "evidence_register_and_validate" in db_actions
    assert "MULTI_HASH_COMPUTED" in combined
    assert "EVIDENCE_VALIDATED" in combined or "INTEGRITY_VERIFIED" in combined
    assert len(combined) >= 2


async def test_pipeline_execution_creates_stage_entries(
    app_client: TestClient,
    seeded_db: dict[str, Any],
) -> None:
    """A full JobRunner pass writes one PIPELINE_STAGE_COMPLETED row per stage."""
    # Arrange
    evidence_id = str(uuid4())
    case_id = str(uuid4())
    user_id = seeded_db["user_ids"]["investigator"]

    # Act
    job_id = await _run_audited_pipeline(
        app_client, evidence_id=evidence_id, case_id=case_id, user_id=user_id
    )

    # Assert
    stage_rows = [
        row
        for row in await _audit_rows(app_client)
        if row.action == "PIPELINE_STAGE_COMPLETED" and row.evidence_id == evidence_id
    ]
    completed_stages = {row.stage for row in stage_rows}
    expected = {stage.value for stage in PipelineStage}
    assert completed_stages == expected
    assert len(stage_rows) == len(PipelineStage)
    for row in stage_rows:
        assert row.user_id == user_id
        assert row.timestamp is not None
        assert job_id in (row.details or "")


async def test_audit_trail_completeness(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """A full workflow leaves a complete audit row for every significant action."""
    # Arrange
    investigator_id = seeded_db["user_ids"]["investigator"]
    headers = _auth(app_client.investigator_token)  # type: ignore[attr-defined]

    # Act
    login = app_client.post(
        "/api/v1/auth/login",
        data={
            "username": TEST_INVESTIGATOR_USERNAME,
            "password": TEST_INVESTIGATOR_PASSWORD,
        },
    )
    assert login.status_code == 200, login.text
    case_id = _open_active_case(app_client, headers, seeded_db)
    evidence_id = _register_evidence(
        app_client, headers, case_id=case_id, tmp_path=tmp_path
    )
    assert (
        app_client.post(
            f"/api/v1/evidence/{evidence_id}/verify-integrity", headers=headers
        ).status_code
        == 200
    )
    await _run_audited_pipeline(
        app_client,
        evidence_id=evidence_id,
        case_id=case_id,
        user_id=investigator_id,
    )

    # Assert
    rows = await _audit_rows(app_client)
    actions = {row.action for row in rows}
    assert "USER_AUTHENTICATED" in actions
    assert "case_created" in actions
    assert "evidence_register_and_validate" in actions
    assert "PIPELINE_JOB_STARTED" in actions
    assert "PIPELINE_JOB_COMPLETED" in actions
    stage_rows = [
        row
        for row in rows
        if row.action == "PIPELINE_STAGE_COMPLETED" and row.evidence_id == evidence_id
    ]
    assert {row.stage for row in stage_rows} == {stage.value for stage in PipelineStage}

    significant = [row for row in rows if row.action in _SIGNIFICANT_ACTIONS]
    assert significant
    for row in significant:
        assert row.timestamp is not None, row.action
        assert row.user_id, row.action
        assert row.action, row.action
        assert row.evidence_id, row.action
        assert row.stage, row.action
