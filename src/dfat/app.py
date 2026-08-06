"""FastAPI application factory for the DFAT REST API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from dfat import __version__
from dfat.container import ApplicationContainer


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle hooks.

    Args:
        app: FastAPI application instance.

    Yields:
        Control to the running application.
    """
    # TODO: Wire startup initialisation in later prompts.
    _ = app
    yield
    # TODO: Wire shutdown cleanup in later prompts.


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

    # Placeholder routers — concrete routes are added in later prompts.
    evidence_router = APIRouter(prefix="/evidence", tags=["evidence"])
    analysis_router = APIRouter(prefix="/analysis", tags=["analysis"])
    reports_router = APIRouter(prefix="/reports", tags=["reports"])
    evaluation_router = APIRouter(prefix="/evaluation", tags=["evaluation"])

    app.include_router(evidence_router)
    app.include_router(analysis_router)
    app.include_router(reports_router)
    app.include_router(evaluation_router)

    return app
