"""Unit tests for CompressionMiddleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from dfat.api.middleware.compression import CompressionMiddleware

_LARGE = "x" * 2048


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/big")
    def big() -> dict[str, str]:
        return {"blob": _LARGE}

    @app.get("/tiny")
    def tiny() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/pdf")
    def pdf() -> Response:
        return Response(content=_LARGE.encode(), media_type="application/pdf")

    app.add_middleware(CompressionMiddleware)
    return TestClient(app)


def test_gzip_compresses_large_json_when_accepted() -> None:
    """Responses larger than 1 KB are gzipped when Accept-Encoding allows it."""
    client = _client()
    raw = client.get("/big", headers={"Accept-Encoding": "identity"})
    compressed = client.get("/big", headers={"Accept-Encoding": "gzip"})

    assert raw.status_code == 200
    assert "gzip" not in raw.headers.get("content-encoding", "")
    assert compressed.status_code == 200
    assert compressed.headers.get("content-encoding") == "gzip"
    encoded_len = int(compressed.headers.get("content-length", "0"))
    assert encoded_len > 0
    assert encoded_len < len(raw.content)
    assert compressed.json() == raw.json()


def test_small_response_is_not_compressed() -> None:
    """Bodies under 1 KB stay uncompressed."""
    client = _client()
    response = client.get("/tiny", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "gzip" not in response.headers.get("content-encoding", "")


def test_pdf_download_is_not_compressed() -> None:
    """PDF responses are excluded from gzip."""
    client = _client()
    response = client.get("/pdf", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "gzip" not in response.headers.get("content-encoding", "")
    assert response.content == _LARGE.encode()
