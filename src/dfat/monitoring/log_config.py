"""Production-grade structured JSON logging with rotation and correlation."""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

import structlog

from dfat.settings import LoggingSettings


class ProductionLogConfig:
    """Configures structured JSON logging for production deployments."""

    @staticmethod
    def configure(settings: LoggingSettings) -> None:
        log_level = getattr(logging, settings.log_level.upper(), logging.WARNING)
        audit_log_path = Path(settings.audit_log_path)
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        error_log_path = audit_log_path.parent / "errors.log"

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        # Clear existing handlers to avoid duplicates on reload.
        root.handlers.clear()

        json_formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","message":"%(message)s"}'
        )

        console = logging.StreamHandler()
        console.setLevel(log_level)
        console.setFormatter(json_formatter)
        root.addHandler(console)

        audit_handler = logging.handlers.RotatingFileHandler(
            str(audit_log_path),
            maxBytes=100 * 1024 * 1024,  # 100 MB
            backupCount=10,
            encoding="utf-8",
        )
        audit_handler.setLevel(logging.DEBUG)
        audit_handler.setFormatter(json_formatter)
        root.addHandler(audit_handler)

        error_handler = logging.handlers.RotatingFileHandler(
            str(error_log_path),
            maxBytes=50 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(json_formatter)
        root.addHandler(error_handler)

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    @staticmethod
    def bind_request_id(request_id: str) -> None:
        """Bind a request correlation ID to the current context."""
        structlog.contextvars.bind_contextvars(request_id=request_id)

    @staticmethod
    def clear_request_context() -> None:
        structlog.contextvars.clear_contextvars()
