"""Timeline generation — chronological views of timestamped artefacts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.parsers.utils import convert_timestamp

_TIMESTAMP_FIELDS: frozenset[str] = frozenset(
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
    }
)


class TimelineEntry(BaseModel):
    """A single timestamped event derived from an artefact field."""

    model_config = ConfigDict(frozen=False)

    timestamp: datetime
    artefact_id: str
    category: ArtefactCategory
    description: str
    source_field: str


class TimelineWindow(BaseModel):
    """A contiguous time window containing timeline entries."""

    model_config = ConfigDict(frozen=False)

    window_start: datetime
    window_end: datetime
    entries: list[TimelineEntry] = Field(default_factory=list)


class Timeline(BaseModel):
    """Chronological timeline of artefact events.

    Attributes:
        entries: All timestamped events in ascending order.
        windows: Entries grouped into fixed-width time windows.
        earliest: Earliest event timestamp (UTC).
        latest: Latest event timestamp (UTC).
        duration_seconds: Span from earliest to latest.
        entry_count: Number of timeline entries.
    """

    model_config = ConfigDict(frozen=False)

    entries: list[TimelineEntry] = Field(default_factory=list)
    windows: list[TimelineWindow] = Field(default_factory=list)
    earliest: Optional[datetime] = None
    latest: Optional[datetime] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_seconds(self) -> float:
        """Return seconds between earliest and latest, or ``0.0`` if empty."""
        if self.earliest is None or self.latest is None:
            return 0.0
        return max(0.0, (self.latest - self.earliest).total_seconds())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entry_count(self) -> int:
        """Return the number of timeline entries."""
        return len(self.entries)


class TimelineGenerator:
    """Extract and chronologically order timestamped artefact fields."""

    def __init__(self, window_seconds: int = 3600) -> None:
        """Initialise the timeline generator.

        Args:
            window_seconds: Width of each grouping window (default 1 hour).
        """
        self._window_seconds = max(1, int(window_seconds))

    def generate(self, artefact_set: ArtefactSet) -> Timeline:
        """Build a chronological timeline from timestamped artefact fields.

        Args:
            artefact_set: Artefact collection to scan for timestamps.

        Returns:
            Sorted ``Timeline`` with fixed-width ``windows`` grouping.
        """
        entries: list[TimelineEntry] = []
        for artefact in artefact_set.artefacts:
            entries.extend(self._entries_from_artefact(artefact))

        entries.sort(key=lambda item: (item.timestamp, item.artefact_id, item.source_field))

        if not entries:
            return Timeline(entries=[], windows=[], earliest=None, latest=None)

        earliest = entries[0].timestamp
        latest = entries[-1].timestamp
        windows = self._group_windows(entries, earliest)
        return Timeline(
            entries=entries,
            windows=windows,
            earliest=earliest,
            latest=latest,
        )

    def _entries_from_artefact(self, artefact: Artefact) -> list[TimelineEntry]:
        """Extract timeline entries from known timestamp fields in ``raw_data``."""
        entries: list[TimelineEntry] = []
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        for field, value in raw.items():
            if not self._is_timestamp_field(field):
                continue
            parsed = convert_timestamp(value)
            if parsed is None:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            else:
                parsed = parsed.astimezone(UTC)
            entries.append(
                TimelineEntry(
                    timestamp=parsed,
                    artefact_id=artefact.artefact_id,
                    category=artefact.category,
                    description=self._describe(artefact, field, parsed),
                    source_field=field,
                )
            )
        return entries

    def _group_windows(
        self,
        entries: list[TimelineEntry],
        earliest: datetime,
    ) -> list[TimelineWindow]:
        """Bucket sorted entries into contiguous windows of ``window_seconds``."""
        width = timedelta(seconds=self._window_seconds)
        windows: list[TimelineWindow] = []
        current_start = earliest
        current_end = earliest + width
        bucket: list[TimelineEntry] = []

        for entry in entries:
            while entry.timestamp >= current_end:
                if bucket:
                    windows.append(
                        TimelineWindow(
                            window_start=current_start,
                            window_end=current_end,
                            entries=list(bucket),
                        )
                    )
                    bucket = []
                current_start = current_end
                current_end = current_start + width
            bucket.append(entry)

        if bucket:
            windows.append(
                TimelineWindow(
                    window_start=current_start,
                    window_end=current_end,
                    entries=bucket,
                )
            )
        return windows

    @staticmethod
    def _is_timestamp_field(field: str) -> bool:
        """Return whether ``field`` should be treated as a timestamp source."""
        if field in _TIMESTAMP_FIELDS:
            return True
        return field.endswith("_time") or field.endswith("_timestamp")

    @staticmethod
    def _describe(artefact: Artefact, field: str, timestamp: datetime) -> str:
        """Build a short human-readable timeline description."""
        category = artefact.category.value
        raw = artefact.raw_data
        detail = TimelineGenerator._primary_label(artefact.category, raw)
        stamp = timestamp.isoformat()
        if detail:
            return f"{category}: {detail} ({field}={stamp})"
        return f"{category}: {field}={stamp}"

    @staticmethod
    def _primary_label(category: ArtefactCategory, raw: dict[str, Any]) -> str:
        """Pick a concise identifying label for an artefact."""
        if category is ArtefactCategory.RUNNING_PROCESS:
            name = raw.get("name") or raw.get("process_name")
            pid = raw.get("pid")
            if name and pid is not None:
                return f"{name} (pid={pid})"
            return str(name or pid or "")
        if category is ArtefactCategory.NETWORK_CONNECTION:
            remote = raw.get("remote_address")
            port = raw.get("remote_port")
            if remote is not None:
                return f"{remote}:{port}" if port is not None else str(remote)
        if category is ArtefactCategory.FILESYSTEM_METADATA:
            return str(raw.get("path") or raw.get("filename") or "")
        if category is ArtefactCategory.REGISTRY_KEY:
            return str(raw.get("key_path") or raw.get("value_name") or "")
        if category is ArtefactCategory.EVENT_LOG:
            event_id = raw.get("event_id")
            return f"event_id={event_id}" if event_id is not None else ""
        if category is ArtefactCategory.BROWSER_HISTORY:
            return str(raw.get("url") or raw.get("title") or "")
        if category is ArtefactCategory.INJECTED_CODE:
            name = raw.get("process_name")
            pid = raw.get("pid")
            if name and pid is not None:
                return f"{name} (pid={pid})"
            return str(name or pid or "")
        return ""
