"""Local filesystem storage with path-traversal protection."""

from __future__ import annotations

from pathlib import Path

from dfat.core.enums import HashAlgorithm
from dfat.core.exceptions import EvidenceError
from dfat.shared.hashing import compute_file_hash


class LocalFileStorage:
    """Filesystem storage constrained to a configured base directory."""

    def __init__(self, base_dir: Path) -> None:
        """Initialise local storage.

        Args:
            base_dir: Root directory that all paths must resolve within.
        """
        self._base_dir = base_dir.resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        """Return the resolved base directory."""
        return self._base_dir

    def read_file(self, file_path: Path) -> bytes:
        """Read a file after validating it lies within ``base_dir``.

        Args:
            file_path: Absolute or relative path to read.

        Returns:
            File contents as bytes.

        Raises:
            EvidenceError: If the path escapes ``base_dir``.
        """
        resolved = self._resolve_within_base(file_path)
        return resolved.read_bytes()

    def write_file(self, file_path: Path, data: bytes) -> Path:
        """Write bytes to a path within ``base_dir``.

        Args:
            file_path: Destination path.
            data: Bytes to write.

        Returns:
            Resolved written path.
        """
        resolved = self._resolve_within_base(file_path, must_exist=False)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(data)
        return resolved

    def file_exists(self, file_path: Path) -> bool:
        """Return True if the path exists within ``base_dir``.

        Args:
            file_path: Candidate path.

        Returns:
            True when the file exists inside the base directory.
        """
        try:
            resolved = self._resolve_within_base(file_path)
        except EvidenceError:
            return False
        return resolved.is_file()

    def list_files(self, directory: Path, pattern: str = "*") -> list[Path]:
        """List files under a directory within ``base_dir``.

        Args:
            directory: Directory to search.
            pattern: Glob pattern.

        Returns:
            Sorted list of matching file paths.
        """
        resolved = self._resolve_within_base(directory, must_exist=False)
        if not resolved.exists():
            return []
        return sorted(path for path in resolved.glob(pattern) if path.is_file())

    def get_file_size(self, file_path: Path) -> int:
        """Return the size of a file in bytes.

        Args:
            file_path: Path to measure.

        Returns:
            File size in bytes.
        """
        resolved = self._resolve_within_base(file_path)
        return resolved.stat().st_size

    def compute_hash(self, file_path: Path, algorithm: HashAlgorithm) -> str:
        """Compute a cryptographic hash of a stored file.

        Args:
            file_path: Path to hash.
            algorithm: Hash algorithm.

        Returns:
            Hexadecimal digest.
        """
        resolved = self._resolve_within_base(file_path)
        return compute_file_hash(resolved, algorithm)

    def _resolve_within_base(
        self,
        file_path: Path,
        *,
        must_exist: bool = True,
    ) -> Path:
        """Resolve a path and ensure it remains within ``base_dir``.

        Args:
            file_path: Candidate path (absolute or relative to base).
            must_exist: Unused flag retained for call-site clarity.

        Returns:
            Resolved absolute path inside ``base_dir``.

        Raises:
            EvidenceError: If the resolved path escapes ``base_dir``.
        """
        _ = must_exist
        candidate = file_path if file_path.is_absolute() else self._base_dir / file_path
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self._base_dir)
        except ValueError as exc:
            raise EvidenceError(
                f"Path escapes storage base directory: {file_path}",
                context={
                    "path": str(file_path),
                    "base_dir": str(self._base_dir),
                    "resolved": str(resolved),
                },
            ) from exc
        return resolved
