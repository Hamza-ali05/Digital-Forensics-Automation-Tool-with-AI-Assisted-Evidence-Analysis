"""API request audit trail middleware."""

from __future__ import annotations

import time
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from dfat.core.enums import PipelineStage
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger


class AuditTrailMiddleware(BaseHTTPMiddleware):
    """Log every API request to the forensic audit trail."""

    def __init__(self, app: object, audit_logger: ForensicAuditLogger) -> None:
        """Initialise middleware.

        Args:
            app: ASGI application.
            audit_logger: Forensic audit logger instance.
        """
        super().__init__(app)  # type: ignore[arg-type]
        self._audit_logger = audit_logger

    def _extract_user_id(self, request: Request) -> Optional[str]:
        """Best-effort extract of authenticated user ID from a Bearer JWT."""
        auth = request.headers.get("Authorization")
        if not auth or not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        try:
            container = request.app.state.container
            jwt_handler = container.auth.jwt_handler()
            claims = jwt_handler.decode_token(token)
            subject = claims.get("sub")
            return str(subject) if subject is not None else None
        except Exception:  # noqa: BLE001 — audit must not fail the request
            return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process a request and emit an audit entry.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler.

        Returns:
            HTTP response.
        """
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        client_host = request.client.host if request.client else "unknown"
        anonymised_ip = (
            ".".join(client_host.split(".")[:2] + ["x", "x"])
            if "." in client_host
            else "anon"
        )
        request_id = getattr(request.state, "request_id", None)
        user_id = self._extract_user_id(request)
        self._audit_logger.log_action(
            stage=PipelineStage.REPORTING,
            action="API_REQUEST",
            evidence_id="api",
            details={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "response_time_ms": round(elapsed_ms, 2),
                "client_ip": anonymised_ip,
                "request_id": request_id,
                "user_id": user_id,
            },
        )
        return response
