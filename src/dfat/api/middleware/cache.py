"""In-memory GET response cache with role-specific keys and TTL."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Optional
from urllib.parse import parse_qsl, urlencode

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

# Full API paths (Prompt 9.8 lists the suffix; the app is mounted at /api/v1).
DEFAULT_CACHE_TTLS: dict[str, int] = {
    "/api/v1/health": 30,
    # Readiness is a live probe — caching it reports stale component state.
    "/api/v1/ai/health": 30,
    "/api/v1/evidence/statistics": 60,
    "/api/v1/pipeline/parsers": 300,
    "/api/v1/evaluation/benchmark/datasets": 600,
    "/api/v1/cases": 30,
}

_EVIDENCE_DETAIL_RE = re.compile(r"^/api/v1/evidence/[^/]+/detail$")
_EVIDENCE_DETAIL_TTL = 30

_PUBLIC_PATHS = frozenset(
    {
        "/api/v1/health",
        "/api/v1/ai/health",
    }
)

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class _CacheEntry:
    """Stored response body and metadata."""

    status_code: int
    headers: list[tuple[str, str]]
    body: bytes
    media_type: Optional[str]
    expires_at: float
    ttl_seconds: int


def _normalize_path(path: str) -> str:
    """Return a cache-key path without a trailing slash (except ``/``)."""
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def _sorted_query(query: str) -> str:
    """Canonicalise query string so param order does not split cache entries."""
    if not query:
        return ""
    return urlencode(sorted(parse_qsl(query, keep_blank_values=True)))


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """In-memory GET cache keyed by path, query string, and user role.

    Successful GET responses for configured endpoints are buffered for a
    per-path TTL. Mutating requests invalidate related cache prefixes.
    ``X-Cache`` is ``HIT`` or ``MISS`` on cacheable responses.
    """

    def __init__(
        self,
        app: object,
        ttl_by_path: Optional[dict[str, int]] = None,
    ) -> None:
        """Initialise the cache.

        Args:
            app: ASGI application.
            ttl_by_path: Optional path → TTL seconds override.
        """
        super().__init__(app)  # type: ignore[arg-type]
        self._ttl_by_path = {
            _normalize_path(path): int(ttl)
            for path, ttl in (ttl_by_path or DEFAULT_CACHE_TTLS).items()
        }
        self._store: dict[tuple[str, str, str], _CacheEntry] = {}
        self._lock = Lock()

    def _ttl_for(self, path: str) -> Optional[int]:
        """Return TTL seconds when ``path`` is cacheable."""
        normalized = _normalize_path(path)
        exact = self._ttl_by_path.get(normalized)
        if exact is not None:
            return exact
        if _EVIDENCE_DETAIL_RE.match(normalized):
            return _EVIDENCE_DETAIL_TTL
        return None

    def _user_role(self, request: Request) -> str:
        """Best-effort JWT ``role`` claim, else ``anonymous``."""
        auth = request.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            return "anonymous"
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return "anonymous"
        try:
            container = request.app.state.container
            jwt_handler = container.auth.jwt_handler()
            claims = jwt_handler.decode_token(token)
            role = claims.get("role")
            return str(role) if role else "anonymous"
        except Exception:  # noqa: BLE001 — unauthenticated cache bucket
            return "anonymous"

    def _cache_key(self, request: Request) -> tuple[str, str, str]:
        """Build the (path, query, role) cache key."""
        return (
            _normalize_path(request.url.path),
            _sorted_query(request.url.query),
            self._user_role(request),
        )

    def _lookup(self, key: tuple[str, str, str]) -> Optional[_CacheEntry]:
        """Return a non-expired cache entry, dropping stale ones."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._store[key]
                return None
            return entry

    def _store_entry(self, key: tuple[str, str, str], entry: _CacheEntry) -> None:
        """Insert or replace a cache entry."""
        with self._lock:
            self._store[key] = entry

    def invalidate_path(self, path: str) -> None:
        """Drop every entry whose path matches ``path`` (any query/role)."""
        target = _normalize_path(path)
        with self._lock:
            stale = [key for key in self._store if key[0] == target]
            for key in stale:
                del self._store[key]

    def invalidate_prefix(self, prefix: str) -> None:
        """Drop entries whose path equals ``prefix`` or is nested under it."""
        target = _normalize_path(prefix)
        nested = target + "/"
        with self._lock:
            stale = [
                key
                for key in self._store
                if key[0] == target or key[0].startswith(nested)
            ]
            for key in stale:
                del self._store[key]

    def clear(self) -> None:
        """Drop the entire cache (testing / admin)."""
        with self._lock:
            self._store.clear()

    def _invalidate_for_mutation(self, path: str) -> None:
        """Clear caches related to a mutating request path."""
        normalized = _normalize_path(path)
        if normalized.startswith("/api/v1/evidence"):
            self.invalidate_prefix("/api/v1/evidence")
        if normalized.startswith("/api/v1/cases"):
            self.invalidate_prefix("/api/v1/cases")
        if normalized.startswith("/api/v1/pipeline"):
            self.invalidate_path("/api/v1/pipeline/parsers")
        if normalized.startswith("/api/v1/evaluation"):
            self.invalidate_path("/api/v1/evaluation/benchmark/datasets")

    def _cache_control(self, path: str, ttl: int) -> str:
        """Build a Cache-Control value for a cached endpoint."""
        scope = "public" if _normalize_path(path) in _PUBLIC_PATHS else "private"
        return f"{scope}, max-age={ttl}"

    def _hit_response(self, entry: _CacheEntry, path: str) -> StarletteResponse:
        """Rebuild a Starlette response from a cache entry."""
        headers = {key: value for key, value in entry.headers}
        headers["x-cache"] = "HIT"
        headers["cache-control"] = self._cache_control(path, entry.ttl_seconds)
        return StarletteResponse(
            content=entry.body,
            status_code=entry.status_code,
            headers=headers,
            media_type=entry.media_type,
        )

    async def _buffer_response(self, response: Response) -> tuple[bytes, StarletteResponse]:
        """Read the downstream body so it can be cached and re-sent."""
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, memoryview):
                chunks.append(chunk.tobytes())
            elif isinstance(chunk, bytes):
                chunks.append(chunk)
            else:
                chunks.append(str(chunk).encode("utf-8"))
        body = b"".join(chunks)
        rebuilt = StarletteResponse(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
            background=getattr(response, "background", None),
        )
        return body, rebuilt

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Serve a cached GET body or forward the request.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler.

        Returns:
            Cached or live HTTP response.
        """
        method = request.method.upper()
        path = request.url.path

        if method in _MUTATING_METHODS:
            self._invalidate_for_mutation(path)
            return await call_next(request)

        ttl = self._ttl_for(path)
        if method != "GET" or ttl is None:
            return await call_next(request)

        key = self._cache_key(request)
        cached = self._lookup(key)
        if cached is not None:
            return self._hit_response(cached, path)

        response = await call_next(request)
        body, rebuilt = await self._buffer_response(response)
        rebuilt.headers["x-cache"] = "MISS"
        rebuilt.headers["cache-control"] = self._cache_control(path, ttl)

        if rebuilt.status_code == 200:
            skip = {"content-length", "x-cache"}
            stored_headers = [
                (name, value)
                for name, value in rebuilt.headers.items()
                if name.lower() not in skip
            ]
            self._store_entry(
                key,
                _CacheEntry(
                    status_code=rebuilt.status_code,
                    headers=stored_headers,
                    body=body,
                    media_type=rebuilt.media_type,
                    expires_at=time.monotonic() + ttl,
                    ttl_seconds=ttl,
                ),
            )
        return rebuilt
