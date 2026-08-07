"""Shared utilities for forensic artefact parsers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

# Windows FILETIME epoch: 1601-01-01 UTC
_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)
# Heuristic thresholds
_UNIX_MS_THRESHOLD = 1_000_000_000_000  # 1e12 — Unix milliseconds
_UNIX_US_THRESHOLD = 100_000_000_000_000  # 1e14 — Unix microseconds (Firefox PRTime)
_WEBKIT_THRESHOLD = 10_000_000_000_000_000  # 1e16 — µs since 1601 (Chrome/WebKit)
_FILETIME_THRESHOLD = 100_000_000_000_000_000  # 1e17 — 100-ns since 1601

_DEFAULT_ENCODINGS = ("utf-8", "latin-1", "cp1252")


def convert_timestamp(raw_timestamp: Any) -> Optional[datetime]:
    """Convert Unix epoch, Windows FILETIME, or string dates to ``datetime``.

    Args:
        raw_timestamp: Candidate timestamp value.

    Returns:
        Timezone-aware UTC ``datetime``, or ``None`` on failure.
    """
    if raw_timestamp is None:
        return None
    if isinstance(raw_timestamp, datetime):
        if raw_timestamp.tzinfo is None:
            return raw_timestamp.replace(tzinfo=UTC)
        return raw_timestamp.astimezone(UTC)

    if isinstance(raw_timestamp, (int, float)):
        value = float(raw_timestamp)
        if value <= 0:
            return None
        try:
            if value >= _FILETIME_THRESHOLD:
                # 100-nanosecond intervals since 1601-01-01
                return _FILETIME_EPOCH + timedelta(microseconds=value / 10.0)
            if value >= _WEBKIT_THRESHOLD:
                # Microseconds since 1601-01-01 (Chrome/WebKit)
                return _FILETIME_EPOCH + timedelta(microseconds=value)
            if value >= _UNIX_US_THRESHOLD:
                # Microseconds since Unix epoch (Firefox PRTime)
                return datetime.fromtimestamp(value / 1_000_000.0, tz=UTC)
            if value >= _UNIX_MS_THRESHOLD:
                return datetime.fromtimestamp(value / 1000.0, tz=UTC)
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(raw_timestamp, str):
        text = raw_timestamp.strip()
        if not text:
            return None
        # Numeric strings
        try:
            if text.isdigit() or (
                text.replace(".", "", 1).isdigit() and text.count(".") < 2
            ):
                return convert_timestamp(float(text))
        except ValueError:
            pass
        normalised = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalised)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    return None


def sanitise_path(path: str) -> str:
    """Normalise forensic image paths to a consistent forward-slash form.

    Args:
        path: Raw path that may use ``\\`` or mixed separators.

    Returns:
        Normalised path using ``/`` separators without duplicate slashes.
    """
    if not path:
        return ""
    normalised = path.replace("\\", "/")
    while "//" in normalised:
        normalised = normalised.replace("//", "/")
    return normalised


def truncate_data(data: Any, max_length: int = 10000) -> Any:
    """Truncate large string/bytes values to bound memory usage.

    Args:
        data: Arbitrary value; only ``str`` / ``bytes`` / ``bytearray`` truncated.
        max_length: Maximum retained length.

    Returns:
        Truncated value when applicable; otherwise ``data`` unchanged.
    """
    if max_length < 0:
        max_length = 0
    if isinstance(data, str):
        if len(data) <= max_length:
            return data
        return data[:max_length]
    if isinstance(data, (bytes, bytearray)):
        if len(data) <= max_length:
            return bytes(data)
        return bytes(data[:max_length])
    return data


def safe_decode(
    data: bytes,
    encodings: Optional[list[str]] = None,
) -> str:
    """Decode bytes trying multiple encodings.

    Args:
        data: Raw bytes to decode.
        encodings: Ordered encodings to try (default utf-8, latin-1, cp1252).

    Returns:
        Decoded string (latin-1 fallback never fails for arbitrary bytes).
    """
    candidates = encodings or list(_DEFAULT_ENCODINGS)
    for encoding in candidates:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1", errors="replace")
