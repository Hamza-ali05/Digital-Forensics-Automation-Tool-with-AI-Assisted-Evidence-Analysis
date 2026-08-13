"""Global exception handler mapping domain errors to HTTP responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from dfat.api.exceptions import RateLimitExceededError
from dfat.api.schemas.responses import ErrorResponse
from dfat.auth.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    AuthenticationError,
    AuthorisationError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenRevokedError,
)
from dfat.case_management.exceptions import (
    CaseNotFoundError,
    InvalidCaseTransitionError,
    NoLeadInvestigatorError,
)
from dfat.core.exceptions import (
    AIEngineError,
    DFATError,
    EvaluationError,
    EvidenceNotFoundError,
    GroundTruthNotFoundError,
    IntegrityVerificationError,
    MetricsCalculationError,
    ParsingError,
    ReportingError,
    UnsupportedFormatError,
)
from dfat.evidence_management.exceptions import (
    EvidenceQuarantinedError,
    EvidenceValidationError,
    InvalidEvidenceTransitionError,
    MIMETypeMismatchError,
)
from dfat.pipeline.exceptions import (
    AllParsersFailedError,
    ParserUnavailableError,
    PipelineCancelledError,
    PipelineJobNotFoundError,
    PipelineStageError,
    PipelineTimeoutError,
)
from dfat.pipeline.job_manager import JobCancellationError, JobNotFoundError
from starlette.exceptions import HTTPException as StarletteHTTPException


def _request_id(request: Request) -> Optional[str]:
    """Extract request ID from request state when present."""
    return getattr(request.state, "request_id", None)


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
            return GlobalExceptionHandler._error_response(request, exc, 404)

        @app.exception_handler(CaseNotFoundError)
        async def _case_not_found(
            request: Request,
            exc: CaseNotFoundError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 404)

        @app.exception_handler(InvalidCaseTransitionError)
        async def _invalid_case_transition(
            request: Request,
            exc: InvalidCaseTransitionError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 409)

        @app.exception_handler(NoLeadInvestigatorError)
        async def _no_lead_investigator(
            request: Request,
            exc: NoLeadInvestigatorError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 400)

        @app.exception_handler(EvidenceValidationError)
        async def _evidence_validation(
            request: Request,
            exc: EvidenceValidationError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 422)

        @app.exception_handler(InvalidEvidenceTransitionError)
        async def _invalid_evidence_transition(
            request: Request,
            exc: InvalidEvidenceTransitionError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 409)

        @app.exception_handler(MIMETypeMismatchError)
        async def _mime_mismatch(
            request: Request,
            exc: MIMETypeMismatchError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 422)

        @app.exception_handler(EvidenceQuarantinedError)
        async def _evidence_quarantined(
            request: Request,
            exc: EvidenceQuarantinedError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 403)

        @app.exception_handler(PipelineJobNotFoundError)
        async def _pipeline_job_not_found(
            request: Request,
            exc: PipelineJobNotFoundError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 404)

        @app.exception_handler(JobNotFoundError)
        async def _job_manager_not_found(
            request: Request,
            exc: JobNotFoundError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 404)

        @app.exception_handler(JobCancellationError)
        async def _job_cancellation(
            request: Request,
            exc: JobCancellationError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 409)

        @app.exception_handler(PipelineTimeoutError)
        async def _pipeline_timeout(
            request: Request,
            exc: PipelineTimeoutError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 504)

        @app.exception_handler(PipelineCancelledError)
        async def _pipeline_cancelled(
            request: Request,
            exc: PipelineCancelledError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 409)

        @app.exception_handler(PipelineStageError)
        async def _pipeline_stage(
            request: Request,
            exc: PipelineStageError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 500)

        @app.exception_handler(ParserUnavailableError)
        async def _parser_unavailable(
            request: Request,
            exc: ParserUnavailableError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 503)

        @app.exception_handler(AllParsersFailedError)
        async def _all_parsers_failed(
            request: Request,
            exc: AllParsersFailedError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 422)

        @app.exception_handler(IntegrityVerificationError)
        async def _integrity(
            request: Request,
            exc: IntegrityVerificationError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 409)

        @app.exception_handler(UnsupportedFormatError)
        async def _unsupported(
            request: Request,
            exc: UnsupportedFormatError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 400)

        @app.exception_handler(ParsingError)
        async def _parsing(request: Request, exc: ParsingError) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 422)

        @app.exception_handler(AIEngineError)
        async def _ai(request: Request, exc: AIEngineError) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 503)

        @app.exception_handler(ReportingError)
        async def _reporting(request: Request, exc: ReportingError) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 500)

        @app.exception_handler(EvaluationError)
        async def _evaluation(request: Request, exc: EvaluationError) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 500)

        @app.exception_handler(GroundTruthNotFoundError)
        async def _ground_truth_missing(
            request: Request,
            exc: GroundTruthNotFoundError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 404)

        @app.exception_handler(MetricsCalculationError)
        async def _metrics(
            request: Request,
            exc: MetricsCalculationError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 422)

        @app.exception_handler(InvalidCredentialsError)
        async def _invalid_credentials(
            request: Request,
            exc: InvalidCredentialsError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 401)

        @app.exception_handler(TokenExpiredError)
        async def _token_expired(
            request: Request,
            exc: TokenExpiredError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 401)

        @app.exception_handler(TokenRevokedError)
        async def _token_revoked(
            request: Request,
            exc: TokenRevokedError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 401)

        @app.exception_handler(AccountLockedError)
        async def _account_locked(
            request: Request,
            exc: AccountLockedError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 423)

        @app.exception_handler(AccountDisabledError)
        async def _account_disabled(
            request: Request,
            exc: AccountDisabledError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 403)

        @app.exception_handler(InsufficientPermissionsError)
        async def _insufficient_permissions(
            request: Request,
            exc: InsufficientPermissionsError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 403)

        @app.exception_handler(AuthorisationError)
        async def _authorisation(
            request: Request,
            exc: AuthorisationError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 403)

        @app.exception_handler(AuthenticationError)
        async def _authentication(
            request: Request,
            exc: AuthenticationError,
        ) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 401)

        @app.exception_handler(RateLimitExceededError)
        async def _rate_limit(
            request: Request,
            exc: RateLimitExceededError,
        ) -> JSONResponse:
            retry_after = int(exc.retry_after_seconds)
            response = GlobalExceptionHandler._error_response(request, exc, 429)
            response.headers["Retry-After"] = str(retry_after)
            return response

        @app.exception_handler(DFATError)
        async def _dfat(request: Request, exc: DFATError) -> JSONResponse:
            return GlobalExceptionHandler._error_response(request, exc, 400)

        @app.exception_handler(RequestValidationError)
        async def _request_validation(
            request: Request,
            exc: RequestValidationError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=422,
                content=ErrorResponse(
                    error_type="RequestValidationError",
                    message="Request validation failed",
                    timestamp=datetime.now(UTC),
                    details={"errors": exc.errors()},
                    request_id=_request_id(request),
                ).model_dump(mode="json"),
            )

        @app.exception_handler(ValidationError)
        async def _pydantic_validation(
            request: Request,
            exc: ValidationError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=422,
                content=ErrorResponse(
                    error_type="ValidationError",
                    message="Validation failed",
                    timestamp=datetime.now(UTC),
                    details={"errors": exc.errors()},
                    request_id=_request_id(request),
                ).model_dump(mode="json"),
            )

        @app.exception_handler(Exception)
        async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
            if isinstance(exc, StarletteHTTPException):
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=dict(exc.headers) if exc.headers else None,
                )
            return JSONResponse(
                status_code=500,
                content=ErrorResponse(
                    error_type=type(exc).__name__,
                    message="Internal server error",
                    timestamp=datetime.now(UTC),
                    details={},
                    request_id=_request_id(request),
                ).model_dump(mode="json"),
            )

    @staticmethod
    def _error_response(
        request: Request,
        exc: DFATError,
        status_code: int,
        *,
        extra_details: Optional[dict[str, Any]] = None,
    ) -> JSONResponse:
        """Build an ``ErrorResponse`` JSON payload including request ID."""
        details = dict(exc.context)
        if extra_details:
            details.update(extra_details)
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                error_type=type(exc).__name__,
                message=exc.message,
                timestamp=exc.timestamp,
                details=details,
                request_id=_request_id(request),
            ).model_dump(mode="json"),
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Backward-compatible helper used by older app factory code."""
    GlobalExceptionHandler.register(app)
