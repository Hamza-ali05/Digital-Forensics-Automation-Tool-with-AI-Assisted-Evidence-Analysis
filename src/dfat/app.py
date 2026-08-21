"""FastAPI application factory for the DFAT REST API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from dfat import __version__
from dfat.api.middleware.audit import AuditTrailMiddleware
from dfat.api.middleware.cache import ResponseCacheMiddleware
from dfat.api.middleware.compression import CompressionMiddleware
from dfat.api.middleware.cors import configure_cors
from dfat.api.middleware.error_handler import GlobalExceptionHandler
from dfat.api.middleware.rate_limiter import RateLimiterMiddleware
from dfat.api.middleware.request_id import RequestIDMiddleware
from dfat.api.middleware.security_headers import SecurityHeadersMiddleware
from dfat.api.middleware.validation import RequestValidationMiddleware
from dfat.api.routes import (
    ai,
    analysis,
    auth,
    cases,
    datasets,
    evaluation,
    evidence,
    evidence_management,
    health,
    knowledge,
    ml,
    monitoring,
    pipeline,
    reports,
    system,
    threat_intel,
    users,
)
from dfat.api.versioning import API_V1_PREFIX
from dfat.bootstrap.models import SystemReadiness
from dfat.bootstrap.startup_report import StartupReportPrinter
from dfat.container import ApplicationContainer, build_application_container

logger = logging.getLogger(__name__)

_OPENAPI_TAGS = [
    {"name": "Auth", "description": "Registration, login, and token lifecycle"},
    {"name": "Users", "description": "User profile and administration"},
    {"name": "Health", "description": "Liveness, readiness, and system diagnostics"},
    {"name": "Cases", "description": "Investigation case lifecycle management"},
    {"name": "Evidence", "description": "Forensic evidence registration and metadata"},
    {
        "name": "Evidence Management",
        "description": "Validation, custody, inventory, and integrity workflows",
    },
    {"name": "Analysis", "description": "Automated analysis pipeline control"},
    {
        "name": "AI Analysis",
        "description": "Local LLaMA-3 classification, summarisation, explanation, and Q&A",
    },
    {
        "name": "Pipeline",
        "description": "Job submission, progress monitoring, and parser inventory",
    },
    {"name": "Reports", "description": "Dual-output forensic report retrieval"},
    {
        "name": "Evaluation",
        "description": "DFRWS/CFReDS benchmark evaluation endpoints",
    },
    {
        "name": "Monitoring",
        "description": "Production monitoring, metrics, and log access",
    },
    {"name": "Datasets", "description": "Dataset intelligence registry and indexing"},
    {"name": "Knowledge", "description": "Vector store, IOC database, and knowledge graph"},
    {"name": "ML", "description": "Model training, registry, experiments, and inference"},
    {
        "name": "Threat Intelligence",
        "description": "YARA/Sigma rules, MITRE coverage, and intel scanning",
    },
    {
        "name": "System",
        "description": "Startup status, runtime monitoring, and system diagnostics",
    },
]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle hooks.

    Runs the bootstrap boot sequencer before serving requests, stores the
    startup report on ``app.state``, and performs graceful shutdown.
    """
    container: ApplicationContainer = app.state.container
    container.logging.setup_app_logging()

    boot_sequencer = container.boot_sequencer()
    startup_report = await boot_sequencer.boot()

    if startup_report.system_status == SystemReadiness.UNAVAILABLE:
        raise SystemExit("DFAT startup failed. Check logs for details.")

    app.state.startup_report = startup_report
    app.state.system_readiness = startup_report.system_status
    app.state.task_manager = container.task_manager()

    printer = StartupReportPrinter()
    try:
        printer.print_report(startup_report)
    except UnicodeEncodeError:
        logger.warning("Could not print startup banner — console encoding unsupported")
    printer.save_report(startup_report, Path("data/outputs/startup_report.json"))

    await app.state.task_manager.start_all()

    shutdown_handler = container.shutdown_handler()
    shutdown_handler.register_signal_handlers()

    try:
        yield
    finally:
        shutdown_handler = container.shutdown_handler()
        await shutdown_handler.shutdown()


def create_app() -> FastAPI:
    """Create and configure the DFAT FastAPI application.

    Middleware order (request path, outermost → innermost):
    RequestID → Compression → SecurityHeaders → CORS → RateLimiter →
    Cache → Audit → RequestValidation → routes / GlobalExceptionHandler.

    CORS is outside the rate limiter so short-circuit 429 responses still
    receive Access-Control-* headers for browser clients.

    Returns:
        Configured FastAPI application with DI container attached.
    """
    container = build_application_container()
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
    # CORS must be outermost so every response (including 4xx/5xx) gets
    # Access-Control-* headers for the React SPA on :3000.
    audit_logger = container.logging.forensic_audit_logger()
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(AuditTrailMiddleware, audit_logger=audit_logger)
    app.add_middleware(ResponseCacheMiddleware)
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CompressionMiddleware)
    app.add_middleware(RequestIDMiddleware)
    configure_cors(app, settings)

    api_prefix = API_V1_PREFIX
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(users.router, prefix=api_prefix)
    app.include_router(cases.router, prefix=api_prefix)
    # Evidence Management routes before legacy Evidence so static paths
    # (/register, /inventory, /statistics) are not captured by /{evidence_id}.
    app.include_router(evidence_management.router, prefix=api_prefix)
    app.include_router(evidence.router, prefix=api_prefix)
    app.include_router(analysis.router, prefix=api_prefix)
    app.include_router(ai.router, prefix=api_prefix)
    app.include_router(pipeline.router, prefix=api_prefix)
    app.include_router(reports.router, prefix=api_prefix)
    app.include_router(evaluation.router, prefix=api_prefix)
    app.include_router(monitoring.router, prefix=api_prefix)
    app.include_router(datasets.router, prefix=api_prefix)
    app.include_router(knowledge.router, prefix=api_prefix)
    app.include_router(ml.router, prefix=api_prefix)
    app.include_router(threat_intel.router, prefix=api_prefix)
    app.include_router(system.router, prefix=api_prefix)

    return app
