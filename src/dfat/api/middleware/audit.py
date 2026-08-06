"""API request audit trail middleware."""

from __future__ import annotations

import time
from typing import Callable

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
            },
        )
        return response
