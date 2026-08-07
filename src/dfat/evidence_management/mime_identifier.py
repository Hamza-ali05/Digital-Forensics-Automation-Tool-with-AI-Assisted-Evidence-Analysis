"""MIME type identification for forensic disk images and memory dumps."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

from dfat.core.enums import EvidenceType

try:
    import magic as _magic  # type: ignore[import-untyped]
except Exception:  # noqa: BLE001 — optional dependency / missing libmagic
    _magic = None

# Magic-byte / libmagic MIME types commonly associated with forensic images.
FORENSIC_MIME_MAP: dict[str, set[str]] = {
    "application/octet-stream": {".dd", ".raw", ".img", ".001", ".mem", ".vmem", ".dmp"},
    "application/x-e01": {".e01"},
    "application/x-ewf": {".e01", ".ex01"},
    "application/x-aff": {".aff", ".afd", ".afm"},
    "application/x-vmdk": {".vmdk"},
    "application/x-vmem": {".vmem"},
    "application/x-lime": {".lime"},
    "application/x-crashdump": {".dmp"},
}

# Extension → preferred MIME mapping for forensic artefacts.
EXTENSION_MIME_MAP: dict[str, str] = {
    ".dd": "application/octet-stream",
    ".raw": "application/octet-stream",
    ".img": "application/octet-stream",
    ".001": "application/octet-stream",
    ".e01": "application/x-e01",
    ".ex01": "application/x-ewf",
    ".aff": "application/x-aff",
    ".vmdk": "application/x-vmdk",
    ".vmem": "application/x-vmem",
    ".mem": "application/octet-stream",
    ".dmp": "application/x-crashdump",
    ".lime": "application/x-lime",
}

_DISK_EXTENSIONS = {".dd", ".raw", ".e01", ".img", ".001", ".ex01", ".aff", ".vmdk"}
_MEMORY_EXTENSIONS = {".raw", ".vmem", ".dmp", ".mem", ".lime"}


class MIMEIdentifier:
    """Identify MIME types via magic bytes with extension fallback."""

    def identify_from_magic(self, file_path: Path) -> Optional[str]:
        """Detect MIME type using ``python-magic`` when available.

        Args:
            file_path: Path to the file to inspect.

        Returns:
            Detected MIME type string, or ``None`` when magic is unavailable
            or detection fails.
        """
        if _magic is None:
            return None
        path = Path(file_path)
        try:
            if hasattr(_magic, "from_file"):
                detected = _magic.from_file(str(path), mime=True)
            else:
                mime = _magic.Magic(mime=True)
                detected = mime.from_file(str(path))
            if isinstance(detected, bytes):
                detected = detected.decode("utf-8", errors="replace")
            detected = str(detected).strip().lower()
            return detected or None
        except Exception:  # noqa: BLE001 — graceful degradation
            return None

    def identify_from_extension(self, file_path: Path) -> str:
        """Map a file extension to a forensic MIME type.

        Args:
            file_path: Path whose suffix is used for lookup.

        Returns:
            MIME type string (defaults to ``application/octet-stream``).
        """
        extension = Path(file_path).suffix.lower()
        if extension in EXTENSION_MIME_MAP:
            return EXTENSION_MIME_MAP[extension]
        guessed, _ = mimetypes.guess_type(str(file_path))
        return (guessed or "application/octet-stream").lower()

    def identify(self, file_path: Path) -> tuple[str, str]:
        """Identify MIME type, preferring magic bytes over extension.

        Args:
            file_path: Path to inspect.

        Returns:
            Tuple of ``(mime_type, detection_method)`` where detection_method
            is ``magic``, ``extension``, or ``stdlib_mimetypes``.
        """
        path = Path(file_path)
        magic_mime = self.identify_from_magic(path)
        if magic_mime is not None:
            # Prefer forensic extension mapping when magic returns generic octets
            # for known forensic image extensions.
            extension = path.suffix.lower()
            if (
                magic_mime == "application/octet-stream"
                and extension in EXTENSION_MIME_MAP
                and EXTENSION_MIME_MAP[extension] != "application/octet-stream"
            ):
                return EXTENSION_MIME_MAP[extension], "extension"
            return magic_mime, "magic"

        extension = path.suffix.lower()
        if extension in EXTENSION_MIME_MAP:
            return EXTENSION_MIME_MAP[extension], "extension"
        guessed, _ = mimetypes.guess_type(str(path))
        return (guessed or "application/octet-stream").lower(), "stdlib_mimetypes"

    def is_forensic_image(
        self,
        mime_type: str,
        file_extension: str,
        *,
        evidence_type: Optional[EvidenceType] = None,
    ) -> bool:
        """Return whether MIME + extension form a valid forensic image combo.

        Args:
            mime_type: Detected or declared MIME type.
            file_extension: File extension including the leading dot.
            evidence_type: Optional declared evidence type for stricter checks.

        Returns:
            ``True`` when the combination is accepted for DFAT registration.
        """
        extension = file_extension.lower()
        if not extension.startswith("."):
            extension = f".{extension}"
        mime = mime_type.lower()

        if evidence_type is EvidenceType.DISK_IMAGE:
            if extension not in _DISK_EXTENSIONS:
                return False
        elif evidence_type is EvidenceType.MEMORY_DUMP:
            if extension not in _MEMORY_EXTENSIONS:
                return False
        elif extension not in (_DISK_EXTENSIONS | _MEMORY_EXTENSIONS):
            return False

        allowed_extensions = FORENSIC_MIME_MAP.get(mime)
        if allowed_extensions is not None:
            return extension in allowed_extensions

        # Unknown MIME: accept when extension alone is a known forensic type.
        return extension in EXTENSION_MIME_MAP
