"""CORS configuration helper for the DFAT API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dfat.settings import DFATSettings


def configure_cors(app: FastAPI, settings: DFATSettings) -> None:
    """Attach CORS middleware using application settings.

    Args:
        app: FastAPI application instance.
        settings: Loaded DFAT settings (reads ``api.cors_allow_origins``).
    """
    origins = list(settings.api.cors_allow_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        allow_credentials=True,
        max_age=600,
    )
