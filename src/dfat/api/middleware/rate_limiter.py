"""In-memory token-bucket rate limiting middleware."""

from __future__ import annotations

import math
import os
import time
from datetime import UTC, datetime
from threading import Lock
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from dfat.api.schemas.responses import ErrorResponse


class TokenBucket:
    """Token-bucket limiter supporting consume and wait-time queries."""

    def __init__(self, rate: float, capacity: int) -> None:
        """Initialise the bucket.

        Args:
            rate: Token refill rate in tokens per second.
            capacity: Maximum number of tokens held.
        """
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.rate = float(rate)
        self.capacity = int(capacity)
        self.tokens = float(capacity)
        self.updated_at = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed wall time."""
        now = time.monotonic()
        elapsed = now - self.updated_at
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.updated_at = now

    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens from the bucket.

        Args:
            tokens: Number of tokens required.

        Returns:
            ``True`` when tokens were consumed; otherwise ``False``.
        """
        self._refill()
        needed = float(tokens)
        if self.tokens >= needed:
            self.tokens -= needed
            return True
        return False

    def time_until_available(self) -> float:
        """Return seconds until at least one token is available."""
        self._refill()
        if self.tokens >= 1.0:
            return 0.0
        deficit = 1.0 - self.tokens
        return deficit / self.rate


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Per-IP token-bucket rate limiter with endpoint-group quotas."""

    # (tokens_per_minute, capacity)
    _AUTH_RATE = (10.0, 10)
    _EVIDENCE_UPLOAD_RATE = (5.0, 5)
    # SPA dashboards fan out many GETs on load; 60/min caused false 429s.
    _GENERAL_RATE = (300.0, 120)
    _BUCKET_TTL_SECONDS = 600.0

    def __init__(self, app: object) -> None:
        """Initialise middleware.

        Args:
            app: ASGI application.
        """
        super().__init__(app)  # type: ignore[arg-type]
        self._buckets: dict[str, tuple[TokenBucket, float]] = {}
        self._lock = Lock()

    def _client_ip(self, request: Request) -> str:
        """Resolve client IP from forwarded or peer address."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def _endpoint_group(self, method: str, path: str) -> str:
        """Classify a request into a rate-limit group."""
        if path.startswith("/api/v1/auth"):
            return "auth"
        if method.upper() == "POST" and path.startswith("/api/v1/evidence"):
            return "evidence_upload"
        return "general"

    def _rate_for_group(self, group: str) -> tuple[float, int]:
        """Select rate/capacity for an endpoint group."""
        if group == "auth":
            return self._AUTH_RATE
        if group == "evidence_upload":
            return self._EVIDENCE_UPLOAD_RATE
        return self._GENERAL_RATE

    def _cleanup_expired(self, now: float) -> None:
        """Drop buckets that have been idle beyond the TTL."""
        expired = [
            key
            for key, (_bucket, last_seen) in self._buckets.items()
            if now - last_seen > self._BUCKET_TTL_SECONDS
        ]
        for key in expired:
            del self._buckets[key]

    def _get_bucket(self, key: str, rate_per_minute: float, capacity: int) -> TokenBucket:
        """Return an existing or newly created token bucket."""
        now = time.monotonic()
        with self._lock:
            self._cleanup_expired(now)
            entry = self._buckets.get(key)
            if entry is None:
                bucket = TokenBucket(rate=rate_per_minute / 60.0, capacity=capacity)
                self._buckets[key] = (bucket, now)
                return bucket
            bucket, _ = entry
            self._buckets[key] = (bucket, now)
            return bucket

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Enforce per-IP rate limits before continuing.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler.

        Returns:
            Downstream response, or HTTP 429 when limited.
        """
        if os.environ.get("DFAT_E2E_SOFT_ACQUIRE") == "1":
            return await call_next(request)

        # Preflight and health probes must not consume the general SPA budget.
        if request.method.upper() == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if path.startswith("/api/v1/health") or path in {"/health", "/ready", "/live"}:
            return await call_next(request)

        ip = self._client_ip(request)
        group = self._endpoint_group(request.method, path)
        rate_per_minute, capacity = self._rate_for_group(group)
        bucket = self._get_bucket(f"{ip}:{group}", rate_per_minute, capacity)

        if not bucket.consume(1):
            retry_after = max(1, int(math.ceil(bucket.time_until_available())))
            request_id = getattr(request.state, "request_id", None)
            body = ErrorResponse(
                error_type="RateLimitExceededError",
                message="Rate limit exceeded",
                timestamp=datetime.now(UTC),
                details={
                    "retry_after_seconds": retry_after,
                    "group": group,
                },
                request_id=request_id,
            ).model_dump(mode="json")
            return JSONResponse(
                status_code=429,
                content=body,
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
