"""FastAPI application factory for the DFAT REST API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dfat import __version__
from dfat.api.middleware.audit import AuditTrailMiddleware
from dfat.api.middleware.cors import configure_cors
from dfat.api.middleware.error_handler import GlobalExceptionHandler
from dfat.api.middleware.rate_limiter import RateLimiterMiddleware
from dfat.api.middleware.request_id import RequestIDMiddleware
from dfat.api.middleware.security_headers import SecurityHeadersMiddleware
from dfat.api.middleware.validation import RequestValidationMiddleware
from dfat.api.routes import analysis, auth, evaluation, evidence, health, reports, users
from dfat.api.versioning import API_V1_PREFIX
from dfat.container import ApplicationContainer

_OPENAPI_TAGS = [
    {"name": "Auth", "description": "Registration, login, and token lifecycle"},
    {"name": "Users", "description": "User profile and administration"},
    {"name": "Health", "description": "Liveness, readiness, and system diagnostics"},
    {"name": "Evidence", "description": "Forensic evidence registration and metadata"},
    {"name": "Analysis", "description": "Automated analysis pipeline control"},
    {"name": "Reports", "description": "Dual-output forensic report retrieval"},
    {
        "name": "Evaluation",
        "description": "DFRWS/CFReDS benchmark evaluation endpoints",
    },
]


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

    settings = container.settings()
    db_engine = container.database.database_engine()
    if settings.database.create_tables_on_startup:
        # Ensure ORM models are registered on Base.metadata.
        import dfat.database  # noqa: F401

        await db_engine.create_tables()

    try:
        yield
    finally:
        await db_engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the DFAT FastAPI application.

    Middleware order (request path, outermost → innermost):
    RequestID → SecurityHeaders → RateLimiter → CORS → Audit →
    RequestValidation → routes / GlobalExceptionHandler.

    Returns:
        Configured FastAPI application with DI container attached.
    """
    container = ApplicationContainer()
    settings = container.settings()

    app = FastAPI(
        title="DFAT — Digital Forensics Automation Tool API",
        version=__version__,
        description=(
            "REST API for the Digital Forensics Automation Tool "
            "with AI-Assisted Evidence Analysis. Supports forensic evidence "
            "management, automated analysis via local LLaMA-3, dual-output "
            "reporting, and DFRWS/CFReDS benchmark evaluation."
        ),
        contact={
            "name": "Muhammad Aaqif Afzaal",
            "email": "100176885@canterbury.ac.uk",
        },
        license_info={"name": "MIT"},
        openapi_tags=_OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )
    app.state.container = container

    # Exception handlers (innermost — catch exceptions from all layers).
    GlobalExceptionHandler.register(app)

    # Middleware registration: last added = outermost on the request path.
    audit_logger = container.logging.forensic_audit_logger()
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(AuditTrailMiddleware, audit_logger=audit_logger)
    configure_cors(app, settings)
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    api_prefix = API_V1_PREFIX
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(users.router, prefix=api_prefix)
    app.include_router(evidence.router, prefix=api_prefix)
    app.include_router(analysis.router, prefix=api_prefix)
    app.include_router(reports.router, prefix=api_prefix)
    app.include_router(evaluation.router, prefix=api_prefix)

    return app
