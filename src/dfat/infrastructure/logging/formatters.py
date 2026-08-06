"""Structured and human-readable logging formatters."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


class JSONLogFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON line.

        Args:
            record: Standard library log record.

        Returns:
            JSON string with timestamp, level, logger, message, and context.
        """
        context: dict[str, Any] = {}
        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in reserved and not key.startswith("_"):
                context[key] = value

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "context": context,
        }
        if record.exc_info:
            context["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=True)


class HumanReadableFormatter(logging.Formatter):
    """Format log records for human-readable console output."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a human-readable line.

        Args:
            record: Standard library log record.

        Returns:
            Formatted string:
            ``[TIMESTAMP] [LEVEL] logger: message | key=value ...``
        """
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        base = (
            f"[{timestamp}] [{record.levelname}] {record.name}: {record.getMessage()}"
        )
        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "taskName",
        }
        extras = [
            f"{key}={value!r}"
            for key, value in record.__dict__.items()
            if key not in reserved and not key.startswith("_")
        ]
        if extras:
            return f"{base} | {' '.join(extras)}"
        return base
