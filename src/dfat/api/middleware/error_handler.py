"""Global exception handler mapping domain errors to HTTP responses."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from dfat.api.schemas.responses import ErrorResponse
from dfat.core.exceptions import (
    AIEngineError,
    DFATError,
    EvaluationError,
    EvidenceNotFoundError,
    IntegrityVerificationError,
    ParsingError,
    ReportingError,
    UnsupportedFormatError,
)


class GlobalExceptionHandler:
    """Register DFAT domain exception handlers on a FastAPI app."""

    @staticmethod
    def register(app: FastAPI) -> None:
        """Attach exception handlers to the application.

        Args:
            app: FastAPI application instance.
        """

        @app.exception_handler(EvidenceNotFoundError)
        async def _evidence_not_found(
            request: Request,
            exc: EvidenceNotFoundError,
        ) -> JSONResponse:
            _ = request
            return GlobalExceptionHandler._error_response(exc, 404)

        @app.exception_handler(IntegrityVerificationError)
        async def _integrity(
            request: Request,
            exc: IntegrityVerificationError,
        ) -> JSONResponse:
            _ = request
            return GlobalExceptionHandler._error_response(exc, 409)

        @app.exception_handler(UnsupportedFormatError)
        async def _unsupported(
            request: Request,
            exc: UnsupportedFormatError,
        ) -> JSONResponse:
            _ = request
            return GlobalExceptionHandler._error_response(exc, 400)

        @app.exception_handler(ParsingError)
        async def _parsing(request: Request, exc: ParsingError) -> JSONResponse:
            _ = request
            return GlobalExceptionHandler._error_response(exc, 422)

        @app.exception_handler(AIEngineError)
        async def _ai(request: Request, exc: AIEngineError) -> JSONResponse:
            _ = request
            return GlobalExceptionHandler._error_response(exc, 503)

        @app.exception_handler(ReportingError)
        async def _reporting(request: Request, exc: ReportingError) -> JSONResponse:
            _ = request
            return GlobalExceptionHandler._error_response(exc, 500)

        @app.exception_handler(EvaluationError)
        async def _evaluation(request: Request, exc: EvaluationError) -> JSONResponse:
            _ = request
            return GlobalExceptionHandler._error_response(exc, 500)

        @app.exception_handler(DFATError)
        async def _dfat(request: Request, exc: DFATError) -> JSONResponse:
            _ = request
            return GlobalExceptionHandler._error_response(exc, 400)

        @app.exception_handler(RequestValidationError)
        async def _request_validation(
            request: Request,
            exc: RequestValidationError,
        ) -> JSONResponse:
            _ = request
            return JSONResponse(
                status_code=422,
                content=ErrorResponse(
                    error_type="RequestValidationError",
                    message="Request validation failed",
                    timestamp=datetime.now(UTC),
                    details={"errors": exc.errors()},
                ).model_dump(mode="json"),
            )

        @app.exception_handler(ValidationError)
        async def _pydantic_validation(
            request: Request,
            exc: ValidationError,
        ) -> JSONResponse:
            _ = request
            return JSONResponse(
                status_code=422,
                content=ErrorResponse(
                    error_type="ValidationError",
                    message="Validation failed",
                    timestamp=datetime.now(UTC),
                    details={"errors": exc.errors()},
                ).model_dump(mode="json"),
            )

        @app.exception_handler(Exception)
        async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
            _ = request
            _ = exc
            return JSONResponse(
                status_code=500,
                content=ErrorResponse(
                    error_type=type(exc).__name__,
                    message="Internal server error",
                    timestamp=datetime.now(UTC),
                    details={},
                ).model_dump(mode="json"),
            )

    @staticmethod
    def _error_response(exc: DFATError, status_code: int) -> JSONResponse:
        """Build an ``ErrorResponse`` JSON payload."""
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                error_type=type(exc).__name__,
                message=exc.message,
                timestamp=exc.timestamp,
                details=dict(exc.context),
            ).model_dump(mode="json"),
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Backward-compatible helper used by older app factory code."""
    GlobalExceptionHandler.register(app)
