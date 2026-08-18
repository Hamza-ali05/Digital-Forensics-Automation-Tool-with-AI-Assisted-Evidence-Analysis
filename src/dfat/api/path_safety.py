"""Path validation helpers for forensic evidence file locations."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath


def assert_no_path_traversal(file_path: str) -> str:
    """Reject evidence paths that attempt directory traversal.

    Args:
        file_path: Candidate path from an API request.

    Returns:
        The original path when it is free of ``..`` segments.

    Raises:
        ValueError: If the path contains parent-directory references.
    """
    raw = (file_path or "").strip()
    if not raw:
        raise ValueError("file_path must not be empty")
    posix_parts = PurePosixPath(raw.replace("\\", "/")).parts
    win_parts = PureWindowsPath(raw).parts
    if ".." in posix_parts or ".." in win_parts:
        raise ValueError("Path traversal is not allowed")
    if raw.startswith("\\\\") or raw.startswith("//"):
        # UNC / unexpected network paths are not accepted as evidence input.
        raise ValueError("Path traversal is not allowed")
    return file_path
