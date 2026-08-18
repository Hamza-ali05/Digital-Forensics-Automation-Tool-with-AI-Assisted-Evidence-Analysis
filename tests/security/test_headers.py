"""HTTP security-header, CORS, rate-limit, and error-leakage tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME

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


def test_security_headers_present_on_all_responses(app_client: TestClient) -> None:
    """OWASP headers are attached to success and error responses."""
    for path, expected in (("/api/v1/health", 200), ("/api/v1/users/me", 401)):
        response = app_client.get(path)
        assert response.status_code == expected, path
        for header in _REQUIRED_HEADERS:
            assert header in response.headers, header


def test_cors_rejects_unauthorized_origins(app_client: TestClient) -> None:
    """Disallowed Origin values are not reflected in CORS allow-origin."""
    evil = "https://evil.example"
    response = app_client.get("/api/v1/health", headers={"Origin": evil})
    allowed = response.headers.get("access-control-allow-origin")
    assert allowed != evil
    preflight = app_client.options(
        "/api/v1/health",
        headers={
            "Origin": evil,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.headers.get("access-control-allow-origin") != evil


def test_rate_limiting_on_auth_endpoints(app_client: TestClient) -> None:
    """Auth endpoints return 429 after the per-IP token bucket is exhausted."""
    unique_ip = "203.0.113.50"
    headers = {"X-Forwarded-For": unique_ip}
    statuses: list[int] = []
    for _ in range(11):
        response = app_client.post(
            "/api/v1/auth/login",
            data={"username": "rate-limit", "password": "not-used-here!"},
            headers=headers,
        )
        statuses.append(response.status_code)
    assert 429 in statuses
    assert statuses[10] == 429
    retry = app_client.post(
        "/api/v1/auth/login",
        data={"username": "rate-limit", "password": "not-used-here!"},
        headers=headers,
    )
    assert retry.status_code == 429
    assert "retry-after" in retry.headers


def test_no_sensitive_data_in_error_responses(app_client: TestClient) -> None:
    """Error payloads omit credentials, secrets, and stack traces."""
    response = app_client.post(
        "/api/v1/auth/login",
        data={"username": TEST_ADMIN_USERNAME, "password": "WrongPass!!!!"},
        headers={"X-Forwarded-For": "198.51.100.20"},
    )
    assert response.status_code == 401
    body = response.text.lower()
    assert TEST_ADMIN_PASSWORD.lower() not in body
    assert "traceback" not in body
    assert "secret_key" not in body
    assert "hashed_password" not in body
    payload = response.json()
    details = payload.get("details") or {}
    for key in details:
        lowered = str(key).lower()
        assert "password" not in lowered
        assert "secret" not in lowered
        assert "traceback" not in lowered
        assert "token" not in lowered or lowered == "token_type"
