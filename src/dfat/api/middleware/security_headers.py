"""OWASP security response headers for forensic API hardening."""

from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cache-Control": "no-store, no-cache, must-revalidate",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach OWASP-recommended security headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process the request and inject security headers.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler.

        Returns:
            HTTP response with security headers applied.
        """
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            if (
                header.lower() == "cache-control"
                and response.headers.get("x-cache")
            ):
                # Preserve Cache-Control set by ResponseCacheMiddleware.
                continue
            response.headers[header] = value
        return response
