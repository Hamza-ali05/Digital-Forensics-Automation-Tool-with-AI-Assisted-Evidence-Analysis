"""FastAPI application factory for the DFAT REST API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dfat import __version__
from dfat.api.middleware.audit import AuditTrailMiddleware
from dfat.api.middleware.error_handler import GlobalExceptionHandler
from dfat.api.middleware.validation import RequestValidationMiddleware
from dfat.api.routes import analysis, evaluation, evidence, reports
from dfat.container import ApplicationContainer


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle hooks.

    Args:
        app: FastAPI application instance.

    Yields:
        Control to the running application.
    """
    container: ApplicationContainer = app.state.container
    container.logging.setup_app_logging()
    yield


def create_app() -> FastAPI:
    """Create and configure the DFAT FastAPI application.

    Returns:
        Configured FastAPI application with DI container attached.
    """
    container = ApplicationContainer()

    app = FastAPI(
        title="DFAT API",
        version=__version__,
        description=(
            "Digital Forensics Automation Tool API exposing the five-stage "
            "pipeline: Acquisition -> Parsing -> AI Triage -> Reporting -> Evaluation."
        ),
        lifespan=_lifespan,
    )
    app.state.container = container

    GlobalExceptionHandler.register(app)

    audit_logger = container.logging.forensic_audit_logger()
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(AuditTrailMiddleware, audit_logger=audit_logger)

    api_prefix = "/api/v1"
    app.include_router(evidence.router, prefix=api_prefix)
    app.include_router(analysis.router, prefix=api_prefix)
    app.include_router(reports.router, prefix=api_prefix)
    app.include_router(evaluation.router, prefix=api_prefix)

    return app
