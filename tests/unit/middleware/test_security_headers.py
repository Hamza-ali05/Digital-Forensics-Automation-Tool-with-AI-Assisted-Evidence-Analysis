"""Unit tests for OWASP SecurityHeadersMiddleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dfat.api.middleware.security_headers import SecurityHeadersMiddleware

_REQUIRED_HEADERS = [
    "x-content-type-options",
    "x-frame-options",
    "x-xss-protection",
    "strict-transport-security",
    "content-security-policy",
    "referrer-policy",
    "permissions-policy",
    "cache-control",
]


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    def boom() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="missing")

    return TestClient(app, raise_server_exceptions=False)


def test_security_headers_present() -> None:
    """Successful responses include all eight OWASP security headers."""
    # Arrange
    client = _client()

    # Act
    response = client.get("/ok")

    # Assert
    assert response.status_code == 200
    for header in _REQUIRED_HEADERS:
        assert header in response.headers


def test_cache_control_no_store() -> None:
    """Cache-Control prevents browser/proxy caching of forensic responses."""
    # Arrange
    client = _client()

    # Act
    response = client.get("/ok")

    # Assert
    assert "no-store" in response.headers["cache-control"]


def test_headers_on_error_response() -> None:
    """Security headers are present even on 4xx responses."""
    # Arrange
    client = _client()

    # Act
    response = client.get("/boom")

    # Assert
    assert response.status_code == 404
    for header in _REQUIRED_HEADERS:
        assert header in response.headers
