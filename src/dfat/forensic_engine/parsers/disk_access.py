"""Low-level pytsk3 wrapper for safe, read-only disk image access."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from dfat.core.enums import PipelineStage
from dfat.core.exceptions import DiskParsingError
from dfat.forensic_engine.parsers.utils import (
    convert_timestamp,
    safe_decode,
    sanitise_path,
)
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

_PYTSK3_HINT = (
    "pytsk3 is required for disk artefact parsing. Install with: pip install pytsk3"
)


class FileEntry(BaseModel):
    """Normalised filesystem entry discovered inside a disk image.

    Attributes:
        name: Entry base name.
        path: Absolute path within the image (forward-slash form).
        size: File size in bytes (0 for directories / unknown).
        inode: Inode / metadata address.
        file_type: ``file``, ``directory``, ``deleted``, or ``unknown``.
        is_deleted: Whether the entry is marked deleted.
        is_allocated: Whether the metadata is allocated.
        created_time: Creation timestamp when available.
        modified_time: Modification timestamp when available.
        accessed_time: Access timestamp when available.
        changed_time: Metadata-change timestamp when available.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    name: str
    path: str
    size: int = 0
    inode: int = 0
    file_type: str = "unknown"
    is_deleted: bool = False
    is_allocated: bool = True
    created_time: Optional[datetime] = None
    modified_time: Optional[datetime] = None
    accessed_time: Optional[datetime] = None
    changed_time: Optional[datetime] = None


class DiskImageAccessor:
    """Low-level pytsk3 wrapper providing safe disk image access.

    All pytsk3 calls are wrapped in try/except converting failures to
    ``DiskParsingError``. Missing ``pytsk3`` raises a helpful ``ImportError``.
    """

    def __init__(self, audit_logger: ForensicAuditLogger) -> None:
        """Initialise the accessor.

        Args:
            audit_logger: ACPO-compliant forensic audit logger.
        """
        self._audit_logger = audit_logger

    def open_image(self, image_path: Path) -> Any:
        """Open a disk image with pytsk3 in read-only mode.

        Args:
            image_path: Path to the disk image file.

        Returns:
            ``pytsk3.Img_Info`` handle.

        Raises:
            ImportError: If ``pytsk3`` is not installed.
            DiskParsingError: If the image cannot be opened.
        """
        pytsk3 = self._require_pytsk3()
        path = Path(image_path)
        try:
            img_info = pytsk3.Img_Info(str(path))
        except ImportError:
            raise
        except Exception as exc:  # noqa: BLE001 — bridge third-party errors
            raise DiskParsingError(
                f"Failed to open disk image: {path}",
                context={"path": str(path), "error": str(exc)},
            ) from exc

        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="DISK_IMAGE_ACCESSOR_OPENED",
            evidence_id="system",
            details={"path": str(path)},
        )
        return img_info

    def get_filesystem(self, img_info: Any, offset: int = 0) -> Any:
        """Open a filesystem view from an image handle.

        When ``offset`` is ``0``, attempts a direct FS open first, then falls
        back to scanning the partition table for an allocated volume.

        Args:
            img_info: Open ``pytsk3.Img_Info`` handle.
            offset: Explicit partition byte offset (non-zero skips volume scan).

        Returns:
            ``pytsk3.FS_Info`` filesystem handle.

        Raises:
            ImportError: If ``pytsk3`` is not installed.
            DiskParsingError: If no filesystem can be opened.
        """
        pytsk3 = self._require_pytsk3()
        if offset != 0:
            return self._open_fs_at(pytsk3, img_info, offset)

        try:
            return self._open_fs_at(pytsk3, img_info, 0)
        except DiskParsingError:
            pass

        try:
            volume = pytsk3.Volume_Info(img_info)
        except Exception as exc:  # noqa: BLE001
            raise DiskParsingError(
                "Failed to open filesystem and volume system",
                context={"error": str(exc)},
            ) from exc

        block_size = int(getattr(getattr(volume, "info", None), "block_size", 0) or 512)
        last_error: Optional[Exception] = None
        for part in volume:
            try:
                flags = int(getattr(part, "flags", 0))
                alloc_flag = getattr(pytsk3, "TSK_VS_PART_FLAG_ALLOC", 1)
                if flags and (flags & alloc_flag) == 0:
                    continue
                part_offset = int(part.start) * block_size
                if part_offset <= 0 and int(getattr(part, "len", 0) or 0) <= 0:
                    continue
                return self._open_fs_at(pytsk3, img_info, part_offset)
            except DiskParsingError as exc:
                last_error = exc
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        raise DiskParsingError(
            "No readable filesystem found in disk image",
            context={
                "error": str(last_error) if last_error is not None else None,
            },
        )

    def walk_filesystem(
        self,
        fs_info: Any,
        path: str = "/",
        max_depth: int = 50,
    ) -> Generator[FileEntry, None, None]:
        """Recursively walk a filesystem yielding ``FileEntry`` objects.

        Circular directory references are skipped via a visited-inode set.
        ``max_depth`` bounds recursion depth.

        Args:
            fs_info: Open ``pytsk3.FS_Info`` handle.
            path: Starting directory path within the image.
            max_depth: Maximum directory nesting depth.

        Yields:
            Normalised ``FileEntry`` records.

        Raises:
            DiskParsingError: If the starting directory cannot be opened.
        """
        start = sanitise_path(path) or "/"
        try:
            directory = fs_info.open_dir(path=start)
        except Exception as exc:  # noqa: BLE001
            raise DiskParsingError(
                f"Failed to open directory: {start}",
                context={"path": start, "error": str(exc)},
            ) from exc

        visited: set[int] = set()
        yield from self._walk_dir(
            fs_info,
            directory,
            start,
            depth=0,
            max_depth=max_depth,
            visited=visited,
        )

    def extract_file_content(
        self,
        fs_info: Any,
        inode: int,
        max_size: int = 10_000_000,
    ) -> Optional[bytes]:
        """Read file content from the image by inode number.

        Args:
            fs_info: Open filesystem handle.
            inode: Metadata address / inode number.
            max_size: Maximum allowed file size in bytes.

        Returns:
            File bytes, or ``None`` if the file exceeds ``max_size`` or
            cannot be read.
        """
        try:
            file_obj = fs_info.open_meta(inode)
            meta = file_obj.info.meta
            if meta is None:
                return None
            size = int(meta.size)
            if size < 0:
                return None
            if size > max_size:
                return None
            if size == 0:
                return b""
            data = file_obj.read_random(0, size)
            return bytes(data)
        except Exception:  # noqa: BLE001 — soft-fail for unreadable inodes
            return None

    def extract_file_to_temp(
        self,
        fs_info: Any,
        inode: int,
        dest_dir: Path,
    ) -> Optional[Path]:
        """Extract a file by inode into ``dest_dir`` for further processing.

        Args:
            fs_info: Open filesystem handle.
            inode: Metadata address / inode number.
            dest_dir: Destination directory (created if missing).

        Returns:
            Path to the extracted temp file, or ``None`` on failure / oversize.
        """
        content = self.extract_file_content(fs_info, inode)
        if content is None:
            return None
        destination = Path(dest_dir)
        try:
            destination.mkdir(parents=True, exist_ok=True)
            out_path = destination / f"inode_{inode}_{uuid4().hex[:8]}.bin"
            out_path.write_bytes(content)
            return out_path
        except OSError:
            return None

    def close(self, img_info: Any) -> None:
        """Release a previously opened image handle when possible.

        Args:
            img_info: ``pytsk3.Img_Info`` handle (or compatible object).
        """
        close = getattr(img_info, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="DISK_IMAGE_ACCESSOR_CLOSED",
            evidence_id="system",
            details={"handle_type": type(img_info).__name__},
        )

    def _walk_dir(
        self,
        fs_info: Any,
        directory: Any,
        path_prefix: str,
        *,
        depth: int,
        max_depth: int,
        visited: set[int],
    ) -> Generator[FileEntry, None, None]:
        """Internal recursive directory walker with cycle / depth guards."""
        if depth > max_depth:
            return
        try:
            entries = list(directory)
        except Exception:  # noqa: BLE001
            return

        for entry in entries:
            try:
                file_entry = self._to_file_entry(entry, path_prefix)
            except Exception:  # noqa: BLE001
                continue
            if file_entry.name in {".", ".."}:
                continue

            inode = file_entry.inode
            if inode and inode in visited:
                continue
            if inode:
                visited.add(inode)

            yield file_entry

            if file_entry.file_type != "directory":
                continue
            if depth >= max_depth:
                continue
            try:
                child = entry.as_directory()
            except Exception:  # noqa: BLE001
                continue
            yield from self._walk_dir(
                fs_info,
                child,
                file_entry.path,
                depth=depth + 1,
                max_depth=max_depth,
                visited=visited,
            )

    def _to_file_entry(self, entry: Any, path_prefix: str) -> FileEntry:
        """Convert a pytsk3 directory entry into a ``FileEntry``."""
        raw_name = entry.info.name.name
        if isinstance(raw_name, (bytes, bytearray)):
            name = safe_decode(bytes(raw_name))
        else:
            name = str(raw_name)
        prefix = sanitise_path(path_prefix) or "/"
        full_path = sanitise_path(prefix.rstrip("/") + "/" + name)

        meta = getattr(entry.info, "meta", None)
        size = int(getattr(meta, "size", 0) or 0) if meta is not None else 0
        inode = int(getattr(meta, "addr", 0) or 0) if meta is not None else 0

        is_dir = False
        is_deleted = False
        is_allocated = True
        if meta is not None:
            try:
                is_dir = meta.type == meta.TYPE_DIR
            except Exception:  # noqa: BLE001
                is_dir = False
            flags = int(getattr(meta, "flags", 0) or 0)
            # TSK_FS_META_FLAG_UNALLOC is commonly 0x01
            is_allocated = (flags & 0x01) == 0
            is_deleted = not is_allocated

        if is_deleted and not is_dir:
            file_type = "deleted"
        elif is_dir:
            file_type = "directory"
        elif meta is not None:
            file_type = "file"
        else:
            file_type = "unknown"

        return FileEntry(
            name=name,
            path=full_path,
            size=size,
            inode=inode,
            file_type=file_type,
            is_deleted=is_deleted,
            is_allocated=is_allocated,
            created_time=self._meta_time(meta, "crtime"),
            modified_time=self._meta_time(meta, "mtime"),
            accessed_time=self._meta_time(meta, "atime"),
            changed_time=self._meta_time(meta, "ctime"),
        )

    @staticmethod
    def _meta_time(meta: Any, attr: str) -> Optional[datetime]:
        """Extract a metadata timestamp attribute as UTC ``datetime``."""
        if meta is None:
            return None
        try:
            value = getattr(meta, attr, None)
        except Exception:  # noqa: BLE001
            return None
        return convert_timestamp(value)

    def _open_fs_at(self, pytsk3: Any, img_info: Any, offset: int) -> Any:
        """Open ``FS_Info`` at a byte offset, wrapping failures."""
        try:
            return pytsk3.FS_Info(img_info, offset=offset)
        except Exception as exc:  # noqa: BLE001
            raise DiskParsingError(
                f"Failed to open filesystem at offset {offset}",
                context={"offset": offset, "error": str(exc)},
            ) from exc

    @staticmethod
    def _require_pytsk3() -> Any:
        """Lazy-import pytsk3 or raise a helpful ``ImportError``."""
        try:
            import pytsk3
        except ImportError as exc:
            raise ImportError(_PYTSK3_HINT) from exc
        return pytsk3
