"""Unit tests for ResponseCacheMiddleware."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dfat.api.middleware.cache import ResponseCacheMiddleware


class _FakeJwt:
    def decode_token(self, token: str) -> dict[str, str]:
        return {"role": token}


class _FakeAuth:
    def jwt_handler(self) -> _FakeJwt:
        return _FakeJwt()


class _FakeContainer:
    auth = _FakeAuth()


def _client() -> TestClient:
    app = FastAPI()
    app.state.container = _FakeContainer()
    hits = {"health": 0, "stats": 0}

    @app.get("/api/v1/health")
    def health() -> dict[str, int]:
        hits["health"] += 1
        return {"n": hits["health"]}

    @app.get("/api/v1/evidence/statistics")
    def statistics() -> dict[str, int]:
        hits["stats"] += 1
        return {"n": hits["stats"]}

    @app.post("/api/v1/evidence/register")
    def register() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/other")
    def other() -> dict[str, str]:
        return {"cached": "no"}

    app.add_middleware(ResponseCacheMiddleware)
    client = TestClient(app)
    client.hits = hits  # type: ignore[attr-defined]
    return client


def test_health_second_request_is_cache_hit() -> None:
    """Cached GET /health returns X-Cache HIT and Cache-Control."""
    client = _client()

    first = client.get("/api/v1/health")
    second = client.get("/api/v1/health")

    assert first.status_code == 200
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert first.json() == second.json()
    assert client.hits["health"] == 1  # type: ignore[attr-defined]
    assert "max-age=30" in second.headers["cache-control"]


def test_cache_is_role_specific() -> None:
    """The same path is stored separately per JWT role."""
    client = _client()

    admin = client.get(
        "/api/v1/evidence/statistics",
        headers={"Authorization": "Bearer admin"},
    )
    analyst = client.get(
        "/api/v1/evidence/statistics",
        headers={"Authorization": "Bearer analyst"},
    )
    admin_again = client.get(
        "/api/v1/evidence/statistics",
        headers={"Authorization": "Bearer admin"},
    )

    assert admin.headers["x-cache"] == "MISS"
    assert analyst.headers["x-cache"] == "MISS"
    assert admin_again.headers["x-cache"] == "HIT"
    assert client.hits["stats"] == 2  # type: ignore[attr-defined]
    assert "private" in admin.headers["cache-control"]


def test_mutating_request_invalidates_statistics_cache() -> None:
    """POST /evidence clears the statistics cache."""
    client = _client()

    first = client.get("/api/v1/evidence/statistics")
    assert first.headers["x-cache"] == "MISS"
    hit = client.get("/api/v1/evidence/statistics")
    assert hit.headers["x-cache"] == "HIT"

    posted = client.post("/api/v1/evidence/register")
    assert posted.status_code == 200

    after = client.get("/api/v1/evidence/statistics")
    assert after.headers["x-cache"] == "MISS"
    assert client.hits["stats"] == 2  # type: ignore[attr-defined]


def test_uncached_path_has_no_x_cache_header() -> None:
    """Endpoints outside the TTL map are not cached."""
    client = _client()
    response = client.get("/other")
    assert response.status_code == 200
    assert "x-cache" not in response.headers


def test_readiness_path_is_not_cached() -> None:
    """GET /health/ready must not be cached so probes see live component state."""
    from dfat.api.middleware.cache import DEFAULT_CACHE_TTLS

    assert "/api/v1/health/ready" not in DEFAULT_CACHE_TTLS
