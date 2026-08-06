"""Helpers for read-only pytsk3 disk image traversal."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterator, Optional


def require_pytsk3() -> Any:
    """Import pytsk3 or raise a helpful ImportError.

    Returns:
        The imported ``pytsk3`` module.

    Raises:
        ImportError: If ``pytsk3`` is not installed.
    """
    try:
        import pytsk3
    except ImportError as exc:
        raise ImportError(
            "pytsk3 is required for disk artefact parsing. Install with: "
            "pip install pytsk3"
        ) from exc
    return pytsk3


def open_image(path: Path) -> Any:
    """Open a disk image with pytsk3 in read-only mode.

    Args:
        path: Path to the disk image.

    Returns:
        ``pytsk3.Img_Info`` handle.
    """
    pytsk3 = require_pytsk3()
    return pytsk3.Img_Info(str(path))


def open_filesystem(img_info: Any, offset: int = 0) -> Any:
    """Open a filesystem from an image handle.

    Args:
        img_info: Open image handle.
        offset: Partition byte offset.

    Returns:
        ``pytsk3.FS_Info`` handle.
    """
    pytsk3 = require_pytsk3()
    return pytsk3.FS_Info(img_info, offset=offset)


def iter_directory(
    fs_info: Any,
    directory: Any,
    path_prefix: str = "/",
) -> Iterator[tuple[str, Any]]:
    """Recursively yield ``(full_path, entry)`` pairs from a directory.

    Args:
        fs_info: Open filesystem handle.
        directory: Directory object to walk.
        path_prefix: Path prefix for entries.

    Yields:
        Tuples of absolute path string and pytsk3 directory entry.
    """
    for entry in directory:
        name = entry.info.name.name
        if name in (b".", b".."):
            continue
        try:
            decoded = name.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            decoded = repr(name)
        full_path = path_prefix.rstrip("/") + "/" + decoded
        yield full_path, entry
        try:
            if entry.info.meta and entry.info.meta.type == entry.info.meta.TYPE_DIR:
                child = entry.as_directory()
                yield from iter_directory(fs_info, child, full_path)
        except Exception:  # noqa: BLE001 - skip unreadable dirs
            continue


def walk_filesystem(
    path: Path,
    offset: int = 0,
) -> Iterator[tuple[str, Any]]:
    """Walk all filesystem entries in a disk image.

    Args:
        path: Disk image path.
        offset: Partition byte offset.

    Yields:
        Tuples of absolute path string and pytsk3 directory entry.
    """
    img = open_image(path)
    fs = open_filesystem(img, offset=offset)
    root = fs.open_dir(path="/")
    yield from iter_directory(fs, root, "/")


def read_file_bytes(fs_info: Any, path: str, max_bytes: int = 50_000_000) -> bytes:
    """Read a file from an open pytsk3 filesystem.

    Args:
        fs_info: Open filesystem handle.
        path: Absolute path within the image.
        max_bytes: Maximum bytes to read.

    Returns:
        File contents (possibly truncated to ``max_bytes``).
    """
    file_obj = fs_info.open(path)
    size = int(file_obj.info.meta.size)
    to_read = min(size, max_bytes)
    data = file_obj.read_random(0, to_read)
    return bytes(data)


def find_files(
    path: Path,
    predicate: Callable[[str], bool],
    offset: int = 0,
    limit: int = 100,
) -> list[tuple[str, bytes]]:
    """Find and read files matching a path predicate.

    Args:
        path: Disk image path.
        predicate: Function returning True for matching paths.
        offset: Partition byte offset.
        limit: Maximum number of matching files to return.

    Returns:
        List of ``(path, content_bytes)`` pairs.
    """
    img = open_image(path)
    fs = open_filesystem(img, offset=offset)
    results: list[tuple[str, bytes]] = []
    for full_path, entry in iter_directory(fs, fs.open_dir(path="/"), "/"):
        if len(results) >= limit:
            break
        if not predicate(full_path):
            continue
        try:
            if not entry.info.meta or entry.info.meta.type == entry.info.meta.TYPE_DIR:
                continue
            content = read_file_bytes(fs, full_path)
            results.append((full_path, content))
        except Exception:  # noqa: BLE001
            continue
    return results


def meta_timestamp(entry: Any, attr: str) -> Optional[str]:
    """Extract an ISO-ish timestamp attribute from a pytsk3 entry.

    Args:
        entry: Directory entry.
        attr: Attribute name such as ``crtime``, ``mtime``, ``atime``.

    Returns:
        String timestamp or None.
    """
    try:
        meta = entry.info.meta
        if meta is None:
            return None
        value = getattr(meta, attr, None)
        if value in (None, 0):
            return None
        return str(value)
    except Exception:  # noqa: BLE001
        return None
