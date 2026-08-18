"""Validation tests for structured logging and request-id propagation."""

from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from dfat.ai_engine.monitoring.ai_monitor import AIMonitor
from dfat.ai_engine.validation.hallucination_guard import HallucinationReport
from dfat.infrastructure.logging.formatters import JSONLogFormatter
from dfat.pipeline.models import PipelineJob
from dfat.pipeline.pipeline_logger import PipelineLogger
from tests.conftest import (
    SAMPLE_EVIDENCE_DIR,
    TEST_INVESTIGATOR_PASSWORD,
    TEST_INVESTIGATOR_USERNAME,
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _open_active_case(
    client: TestClient, headers: dict[str, str], seeded_db: dict[str, Any]
) -> str:
    created = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "Logging Validation", "description": "prompt-9.12"},
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


def _audit_file_text(client: TestClient) -> str:
    audit_logger = client.app.state.container.logging.forensic_audit_logger()
    path = Path(audit_logger._audit_log_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _audit_entries(client: TestClient) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in _audit_file_text(client).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        loaded = json.loads(stripped)
        entry = loaded.get("entry", loaded)
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def test_structured_logs_are_json() -> None:
    """Application log formatter emits one valid JSON object per record."""
    # Arrange
    formatter = JSONLogFormatter()
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger("dfat.validation.structured")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Act
    logger.info("pipeline.job_start", extra={"job_id": "job-1", "stage": "acquisition"})
    payload = json.loads(stream.getvalue().strip())

    # Assert
    assert payload["level"] == "INFO"
    assert payload["logger"] == "dfat.validation.structured"
    assert payload["message"] == "pipeline.job_start"
    assert "timestamp" in payload
    assert payload["context"]["job_id"] == "job-1"
    assert payload["context"]["stage"] == "acquisition"


def test_request_id_propagated(app_client: TestClient) -> None:
    """Incoming X-Request-ID is echoed and recorded on the API_REQUEST audit entry."""
    # Arrange
    request_id = f"req-9-12-{uuid4().hex[:12]}"

    # Act
    response = app_client.get(
        "/api/v1/health",
        headers={"X-Request-ID": request_id},
    )

    # Assert
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == request_id
    matches = [
        entry
        for entry in _audit_entries(app_client)
        if entry.get("action") == "API_REQUEST"
        and (entry.get("details") or {}).get("request_id") == request_id
    ]
    assert matches, "request_id should appear in audit log entries for the request"
    details = matches[-1]["details"]
    assert details["path"] == "/api/v1/health"
    assert details["method"] == "GET"


async def test_log_levels_correct() -> None:
    """ERROR is used for exceptions, INFO for normal ops, WARNING for degraded state."""
    # Arrange
    formatter = JSONLogFormatter()
    captured: list[dict[str, Any]] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(json.loads(self.format(record)))

    handler = _CaptureHandler()
    handler.setFormatter(formatter)
    logger = logging.getLogger("dfat.validation.levels")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Act — JSON formatter levels
    logger.info("normal operation")
    logger.warning("degraded state: llm unavailable")
    try:
        raise RuntimeError("simulated failure")
    except RuntimeError:
        logger.exception("unhandled exception")

    # Act — pipeline logger (INFO for start, ERROR for parser failures)
    mock_log = MagicMock()
    pipeline_logger = PipelineLogger(audit_service=AsyncMock(), app_logger=mock_log)
    job = PipelineJob(
        evidence_id=str(uuid4()),
        case_id=str(uuid4()),
        user_id="user-1",
    )
    await pipeline_logger.log_job_start(job)
    await pipeline_logger.log_parser_error(job.job_id, "FileSystemParser", "hive corrupt")

    # Act — AI monitor uses WARNING for hallucination (degraded AI quality)
    ai_logger = logging.getLogger("dfat.ai_engine.monitoring.ai_monitor")
    ai_logger.handlers.clear()
    ai_logger.addHandler(handler)
    ai_logger.setLevel(logging.WARNING)
    ai_logger.propagate = False
    monitor = AIMonitor(audit_service=AsyncMock(), app_logger=ai_logger)
    await monitor.log_hallucination_detected(
        "req-hallu",
        HallucinationReport(
            hallucinated_ids=["art-missing"],
            fabricated_terms=["rootkit_trace"],
            risk_level="high",
        ),
    )

    # Assert
    by_level = {item["level"]: item for item in captured if item["logger"].endswith("levels")}
    assert by_level["INFO"]["message"] == "normal operation"
    assert by_level["WARNING"]["message"].startswith("degraded state")
    assert by_level["ERROR"]["message"] == "unhandled exception"
    mock_log.info.assert_called()
    mock_log.error.assert_called()
    hallu = [
        item
        for item in captured
        if "hallucination" in item["message"].lower()
    ]
    assert hallu
    assert hallu[-1]["level"] == "WARNING"


async def test_sensitive_data_not_logged(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Passwords, tokens, and evidence file contents must not appear in logs."""
    # Arrange
    marker = f"SECRET_EVIDENCE_BODY_9_12_{uuid4().hex}"
    headers = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _open_active_case(app_client, headers, seeded_db)
    path = tmp_path / "secret.dd"
    path.write_bytes(
        (SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes() + marker.encode("utf-8")
    )

    # Act
    login = app_client.post(
        "/api/v1/auth/login",
        data={
            "username": TEST_INVESTIGATOR_USERNAME,
            "password": TEST_INVESTIGATOR_PASSWORD,
        },
    )
    assert login.status_code == 200, login.text
    access_token = login.json()["access_token"]
    refresh_token = login.json()["refresh_token"]
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": "sensitive-log-check",
        },
    )
    assert registered.status_code == 201, registered.text

    monitor = AIMonitor(audit_service=AsyncMock())
    await monitor.log_llm_request(
        "generate",
        "llama3",
        prompt_tokens=12,
        job_id="job-sensitive",
    )

    # Assert
    blob = _audit_file_text(app_client)
    assert TEST_INVESTIGATOR_PASSWORD not in blob
    assert access_token not in blob
    assert refresh_token not in blob
    assert marker not in blob
    for entry in _audit_entries(app_client):
        dumped = json.dumps(entry, default=str)
        assert TEST_INVESTIGATOR_PASSWORD not in dumped
        assert access_token not in dumped
        assert marker not in dumped
        details = entry.get("details") or {}
        for key in details:
            lowered = str(key).lower()
            assert lowered not in {"password", "token", "access_token", "prompt"}
    # Authorization header is never copied into audit details.
    assert all(
        "authorization" not in json.dumps(entry.get("details") or {}).lower()
        for entry in _audit_entries(app_client)
        if entry.get("action") == "API_REQUEST"
    )
