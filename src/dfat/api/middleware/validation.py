"""Request validation middleware for Content-Type and size limits."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from dfat.api.schemas.responses import ErrorResponse

_FORM_CONTENT_TYPES = (
    "application/x-www-form-urlencoded",
    "multipart/form-data",
)


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate Content-Type headers and request body size limits."""

    def __init__(
        self,
        app: object,
        *,
        max_body_bytes: int = 10 * 1024 * 1024,
        require_json_methods: frozenset[str] | None = None,
    ) -> None:
        """Initialise middleware.

        Args:
            app: ASGI application.
            max_body_bytes: Maximum allowed request body size.
            require_json_methods: HTTP methods that must send JSON.
        """
        super().__init__(app)  # type: ignore[arg-type]
        self._max_body_bytes = max_body_bytes
        self._require_json_methods = require_json_methods or frozenset(
            {"POST", "PUT", "PATCH"}
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate request headers/size then continue.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler.

        Returns:
            HTTP response, or 413/415 on validation failure.
        """
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                size = 0
            if size > self._max_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content=ErrorResponse(
                        error_type="PayloadTooLarge",
                        message=f"Request body exceeds {self._max_body_bytes} bytes",
                        timestamp=datetime.now(UTC),
                        details={"max_body_bytes": self._max_body_bytes},
                    ).model_dump(mode="json"),
                )

        if (
            request.method in self._require_json_methods
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/v1/auth/login"
        ):
            content_type = request.headers.get("content-type", "")
            lowered = content_type.lower()
            is_json = "application/json" in lowered
            is_form = any(form_type in lowered for form_type in _FORM_CONTENT_TYPES)
            if content_type and not is_json and not is_form:
                return JSONResponse(
                    status_code=415,
                    content=ErrorResponse(
                        error_type="UnsupportedMediaType",
                        message="Content-Type must be application/json",
                        timestamp=datetime.now(UTC),
                        details={"content_type": content_type},
                    ).model_dump(mode="json"),
                )

        return await call_next(request)
