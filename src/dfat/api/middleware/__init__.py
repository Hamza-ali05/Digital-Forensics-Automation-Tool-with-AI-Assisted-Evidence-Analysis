"""DFAT API Middleware — Security, audit, rate limiting, and exception handling."""

from dfat.api.middleware.audit import AuditTrailMiddleware
from dfat.api.middleware.cors import configure_cors
from dfat.api.middleware.error_handler import GlobalExceptionHandler
from dfat.api.middleware.rate_limiter import RateLimiterMiddleware, TokenBucket
from dfat.api.middleware.request_id import RequestIDMiddleware
from dfat.api.middleware.security_headers import SecurityHeadersMiddleware
from dfat.api.middleware.validation import RequestValidationMiddleware

__all__ = [
    "AuditTrailMiddleware",
    "GlobalExceptionHandler",
    "RateLimiterMiddleware",
    "RequestIDMiddleware",
    "RequestValidationMiddleware",
    "SecurityHeadersMiddleware",
    "TokenBucket",
    "configure_cors",
]
