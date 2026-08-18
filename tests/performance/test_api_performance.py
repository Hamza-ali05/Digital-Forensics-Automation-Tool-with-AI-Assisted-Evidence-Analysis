"""HTTP API latency tests for cached and serialised endpoints.

Marked ``performance`` so default pytest runs skip them.
Timing uses an in-process httpx ASGI client so measurements exclude
TestClient's thread-bridge overhead.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import ForensicReport, JSONReport, NarrativeReport
from tests.conftest import SAMPLE_EVIDENCE_DIR


def _elapsed_ms(started: float) -> float:
    """Return milliseconds since ``started``."""
    return (time.perf_counter() - started) * 1000.0


def _auth(client: TestClient, role: str = "investigator") -> dict[str, str]:
    """Return a Bearer header for a seeded TestClient token."""
    token = getattr(client, f"{role}_token")
    return {"Authorization": f"Bearer {token}"}


def _asgi_client(app: Any) -> httpx.AsyncClient:
    """Return an async in-process client bound to ``app``."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


def _open_active_case(
    client: TestClient,
    headers: dict[str, str],
    seeded_db: dict[str, Any],
) -> str:
    """Create, assign, open, and activate a case; return its id."""
    created = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "API Perf Case", "description": "prompt-9.8"},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    assign = client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=headers,
        json={"user_id": seeded_db["user_ids"]["investigator"], "role": "lead"},
    )
    assert assign.status_code == 200, assign.text
    assert client.post(f"/api/v1/cases/{case_id}/open", headers=headers).status_code == 200
    assert (
        client.post(f"/api/v1/cases/{case_id}/activate", headers=headers).status_code
        == 200
    )
    return case_id


@pytest.mark.performance
async def test_health_endpoint_under_10ms(app_client: TestClient) -> None:
    """Cached GET /health completes in under 10 ms."""
    async with _asgi_client(app_client.app) as client:
        warmup = await client.get("/api/v1/health")
        assert warmup.status_code == 200
        samples: list[float] = []
        last_cache = ""
        for _ in range(8):
            started = time.perf_counter()
            response = await client.get("/api/v1/health")
            samples.append(_elapsed_ms(started))
            assert response.status_code == 200
            last_cache = response.headers.get("x-cache", "")
        assert last_cache == "HIT"
        assert min(samples) < 10, (
            f"health min {min(samples):.1f}ms samples={samples!r} (budget 10ms)"
        )


@pytest.mark.performance
async def test_case_list_under_100ms(app_client: TestClient) -> None:
    """GET /cases for a small list completes in under 100 ms."""
    headers = _auth(app_client)
    created = app_client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "List Perf", "description": "n"},
    )
    assert created.status_code == 201, created.text

    async with _asgi_client(app_client.app) as client:
        warmup = await client.get("/api/v1/cases", headers=headers)
        assert warmup.status_code == 200
        started = time.perf_counter()
        response = await client.get("/api/v1/cases", headers=headers)
        elapsed = _elapsed_ms(started)
        assert response.status_code == 200
        assert response.json()["total"] >= 1
        assert response.headers.get("x-cache") == "HIT"
        assert elapsed < 100, f"case list took {elapsed:.1f}ms (budget 100ms)"


@pytest.mark.performance
async def test_evidence_detail_under_100ms(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """GET /evidence/{id}/detail completes in under 100 ms."""
    headers = _auth(app_client)
    case_id = _open_active_case(app_client, headers, seeded_db)
    path = tmp_path / "perf.dd"
    path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": "api-perf",
        },
    )
    assert registered.status_code == 201, registered.text
    evidence_id = registered.json()["evidence_id"]
    detail_url = f"/api/v1/evidence/{evidence_id}/detail"

    async with _asgi_client(app_client.app) as client:
        warmup = await client.get(detail_url, headers=headers)
        assert warmup.status_code == 200, warmup.text
        started = time.perf_counter()
        response = await client.get(detail_url, headers=headers)
        elapsed = _elapsed_ms(started)
        assert response.status_code == 200
        assert response.json()["evidence_id"] == evidence_id
        assert response.headers.get("x-cache") == "HIT"
        assert elapsed < 100, f"evidence detail took {elapsed:.1f}ms (budget 100ms)"


@pytest.mark.performance
async def test_report_json_under_200ms(
    app_client: TestClient,
    sample_case_metadata: CaseMetadata,
) -> None:
    """GET /reports/{id}/json completes in under 200 ms."""
    report = ForensicReport(
        report_id="rep-perf-1",
        case=sample_case_metadata,
        json_report=JSONReport(
            report_id="json-perf-1",
            evidence_id="ev-perf-1",
            artefact_data=[],
            integrity_hash="d" * 64,
        ),
        narrative_report=NarrativeReport(
            report_id="narr-perf-1",
            evidence_id="ev-perf-1",
            summary_text="Narrative body",
            llm_model_used="Mock",
            generation_parameters={},
        ),
        pipeline_duration_seconds=1.5,
        stage_timings={},
    )
    container = app_client.app.state.container
    service = AsyncMock()
    service.get_json_report = AsyncMock(return_value=report.json_report)
    container.services.report_service.override(service)
    headers = _auth(app_client, role="analyst")
    try:
        url = "/api/v1/reports/rep-perf-1/json"
        async with _asgi_client(app_client.app) as client:
            assert (await client.get(url, headers=headers)).status_code == 200
            samples: list[float] = []
            for _ in range(5):
                started = time.perf_counter()
                response = await client.get(url, headers=headers)
                samples.append(_elapsed_ms(started))
                assert response.status_code == 200
                assert response.json()["integrity_hash"] == "d" * 64
            assert min(samples) < 200, (
                f"report json min {min(samples):.1f}ms samples={samples!r} (budget 200ms)"
            )
    finally:
        container.services.report_service.reset_override()


@pytest.mark.performance
async def test_concurrent_requests_stable(app_client: TestClient) -> None:
    """Ten concurrent GET /health calls all succeed within 500 ms each."""
    async with _asgi_client(app_client.app) as client:
        await client.get("/api/v1/health")

        async def _one() -> tuple[int, float]:
            started = time.perf_counter()
            response = await client.get("/api/v1/health")
            return response.status_code, _elapsed_ms(started)

        results = await asyncio.gather(*[_one() for _ in range(10)])

    for status_code, elapsed in results:
        assert status_code == 200
        assert elapsed < 500, f"concurrent health took {elapsed:.1f}ms (budget 500ms)"
