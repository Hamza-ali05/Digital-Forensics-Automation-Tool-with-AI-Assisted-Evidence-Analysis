"""Gzip compression for JSON/text API responses larger than 1 KiB."""

from __future__ import annotations

import gzip
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

_MIN_SIZE_BYTES = 1024

_SKIP_MEDIA_PREFIXES = (
    "application/pdf",
    "application/zip",
    "application/gzip",
    "application/octet-stream",
    "image/",
    "video/",
    "audio/",
    "font/",
)


def _accepts_gzip(request: Request) -> bool:
    """Return whether the client lists gzip in Accept-Encoding."""
    accept = request.headers.get("accept-encoding", "")
    return "gzip" in accept.lower()


def _is_binary_download(request: Request, content_type: str) -> bool:
    """Return True for PDF (and similar binary) downloads that must not gzip."""
    path = request.url.path.lower()
    if path.endswith(".pdf") or "/export/pdf" in path:
        return True
    lowered = content_type.lower()
    return any(lowered.startswith(prefix) for prefix in _SKIP_MEDIA_PREFIXES)


class CompressionMiddleware(BaseHTTPMiddleware):
    """Gzip responses larger than 1 KB when the client accepts encoding.

    Sets ``Content-Encoding: gzip`` and a matching ``Content-Length``. PDF
    and other binary downloads are passed through uncompressed.
    """

    def __init__(self, app: object, min_size: int = _MIN_SIZE_BYTES) -> None:
        """Initialise gzip middleware.

        Args:
            app: ASGI application.
            min_size: Minimum uncompressed body size in bytes to compress.
        """
        super().__init__(app)  # type: ignore[arg-type]
        self._min_size = max(0, int(min_size))

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Compress eligible responses on the way out.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler.

        Returns:
            Original or gzip-compressed HTTP response.
        """
        response = await call_next(request)
        if request.method.upper() == "HEAD":
            return response
        if not _accepts_gzip(request):
            return response
        if response.headers.get("content-encoding"):
            return response

        content_type = response.headers.get("content-type", "")
        if _is_binary_download(request, content_type):
            return response

        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, memoryview):
                chunks.append(chunk.tobytes())
            elif isinstance(chunk, bytes):
                chunks.append(chunk)
            else:
                chunks.append(str(chunk).encode("utf-8"))
        body = b"".join(chunks)

        if len(body) < self._min_size:
            return StarletteResponse(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=getattr(response, "background", None),
            )

        compressed = gzip.compress(body)
        headers = dict(response.headers)
        headers["content-encoding"] = "gzip"
        headers["content-length"] = str(len(compressed))
        vary = headers.get("vary")
        if vary:
            if "accept-encoding" not in vary.lower():
                headers["vary"] = f"{vary}, Accept-Encoding"
        else:
            headers["vary"] = "Accept-Encoding"
        return StarletteResponse(
            content=compressed,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
            background=getattr(response, "background", None),
        )
