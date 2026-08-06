"""DFAT API Routes — HTTP endpoints for auth, health, evidence, and analysis."""

from dfat.api.routes import analysis, auth, evaluation, evidence, health, reports, users

__all__ = [
    "analysis",
    "auth",
    "evaluation",
    "evidence",
    "health",
    "reports",
    "users",
]
