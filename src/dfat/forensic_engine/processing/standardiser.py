"""Artefact standardisation — UTC timestamps, paths, keys, and string hygiene."""

from __future__ import annotations

import re
from typing import Any

from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.parsers.utils import convert_timestamp, sanitise_path

_TIMESTAMP_KEY_HINTS: frozenset[str] = frozenset(
    {
        "timestamp",
        "create_time",
        "created_time",
        "created",
        "exit_time",
        "modified_time",
        "accessed_time",
        "changed_time",
        "last_modified",
        "last_write_time",
        "last_visit_time",
        "parsed_at",
        "extraction_timestamp",
    }
)

_PATH_KEY_HINTS: frozenset[str] = frozenset(
    {
        "path",
        "source_path",
        "filename",
        "key_path",
        "hive_path",
        "file_path",
        "image_path",
        "command_line",  # often contains paths; only normalise if looks like a path
    }
)

_DRIVE_LETTER_RE = re.compile(r"^([A-Za-z]):([/\\].*)$")
_CAMEL_BOUNDARY_RE = re.compile(r"([a-z0-9])([A-Z])")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


class ArtefactStandardiser:
    """Standardise artefact ``raw_data`` fields for consistent downstream use."""

    def standardise(self, artefact_set: ArtefactSet) -> ArtefactSet:
        """Apply timestamp, path, string, and key-name normalisation.

        For each artefact:
            1. Convert timestamp fields to UTC ISO-8601 strings.
            2. Normalise file paths (forward slashes, lowercase drive letters).
            3. Trim whitespace from string fields.
            4. Ensure consistent key naming (snake_case).
            5. Set ``metadata["standardised"] = True``.

        Args:
            artefact_set: Categorised (or raw) artefact collection.

        Returns:
            New ``ArtefactSet`` with standardised artefacts.
        """
        standardised = [self._standardise_artefact(item) for item in artefact_set.artefacts]
        return artefact_set.model_copy(update={"artefacts": standardised})

    def _standardise_artefact(self, artefact: Artefact) -> Artefact:
        """Standardise one artefact's ``raw_data``, ``source_path``, and metadata."""
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        normalised_raw = self._standardise_mapping(raw)

        source_path = artefact.source_path
        if isinstance(source_path, str) and source_path.strip():
            source_path = self._normalise_path(source_path)
        elif isinstance(source_path, str):
            source_path = source_path.strip() or None

        metadata = dict(artefact.metadata)
        metadata["standardised"] = True

        return artefact.model_copy(
            update={
                "raw_data": normalised_raw,
                "source_path": source_path,
                "metadata": metadata,
            }
        )

    def _standardise_mapping(self, data: dict[str, Any]) -> dict[str, Any]:
        """Snake_case keys and recursively standardise values."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            snake_key = self._to_snake_case(str(key))
            result[snake_key] = self._standardise_value(snake_key, value)
        return result

    def _standardise_value(self, key: str, value: Any) -> Any:
        """Standardise a single value based on key hints and runtime type."""
        if value is None:
            return None

        if isinstance(value, dict):
            return self._standardise_mapping(value)

        if isinstance(value, list):
            return [self._standardise_value(key, item) for item in value]

        if isinstance(value, tuple):
            return [self._standardise_value(key, item) for item in value]

        if self._is_timestamp_key(key):
            converted = convert_timestamp(value)
            if converted is not None:
                return converted.isoformat()
            if isinstance(value, str):
                return value.strip()
            return value

        if isinstance(value, str):
            trimmed = value.strip()
            if self._is_path_key(key) or self._looks_like_path(trimmed):
                return self._normalise_path(trimmed)
            return trimmed

        if isinstance(value, (bytes, bytearray)):
            try:
                return bytes(value).decode("utf-8", errors="replace").strip()
            except Exception:  # noqa: BLE001
                return value

        return value

    @staticmethod
    def _is_timestamp_key(key: str) -> bool:
        """Return whether ``key`` names a timestamp field."""
        if key in _TIMESTAMP_KEY_HINTS:
            return True
        return key.endswith("_time") or key.endswith("_timestamp") or key.endswith("_at")

    @staticmethod
    def _is_path_key(key: str) -> bool:
        """Return whether ``key`` names a filesystem/registry path field."""
        if key in _PATH_KEY_HINTS:
            return key != "command_line"
        return key.endswith("_path") or key.endswith("_dir") or key.endswith("_folder")

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        """Heuristic: Windows drive path or UNC / absolute Unix path."""
        if not value or len(value) < 2:
            return False
        if _DRIVE_LETTER_RE.match(value):
            return True
        if value.startswith(("\\\\", "//", "/")):
            return True
        return False

    @staticmethod
    def _normalise_path(path: str) -> str:
        """Forward-slash paths with lowercase drive letters."""
        normalised = sanitise_path(path.strip())
        match = _DRIVE_LETTER_RE.match(normalised)
        if match:
            return f"{match.group(1).lower()}:{match.group(2)}"
        # UNC: keep leading // after sanitise (sanitise collapses // — restore UNC)
        if path.lstrip().startswith("\\\\") or path.lstrip().startswith("//"):
            body = normalised.lstrip("/")
            return "//" + body
        return normalised

    @staticmethod
    def _to_snake_case(key: str) -> str:
        """Convert ``key`` to lower snake_case."""
        text = key.strip()
        if not text:
            return text
        # Already snake_case-ish
        if " " not in text and "-" not in text and text == text.lower() and "_" in text:
            return text
        text = text.replace(" ", "_").replace("-", "_")
        text = _CAMEL_BOUNDARY_RE.sub(r"\1_\2", text)
        text = text.lower()
        text = _NON_ALNUM_RE.sub("_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text
