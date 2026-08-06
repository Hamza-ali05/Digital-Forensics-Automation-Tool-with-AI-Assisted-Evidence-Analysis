"""In-memory LRU cache for artefact sets."""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from dfat.core.models.artefact import ArtefactSet


class InMemoryArtefactCache:
    """OrderedDict-based LRU cache for ``ArtefactSet`` values."""

    def __init__(self, max_size: int = 100) -> None:
        """Initialise the cache.

        Args:
            max_size: Maximum number of entries retained.
        """
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self._max_size = max_size
        self._entries: OrderedDict[str, ArtefactSet] = OrderedDict()

    def get(self, key: str) -> Optional[ArtefactSet]:
        """Return a cached artefact set, marking it as most recently used.

        Args:
            key: Cache key.

        Returns:
            Cached artefact set if present; otherwise None.
        """
        if key not in self._entries:
            return None
        self._entries.move_to_end(key)
        return self._entries[key]

    def set(self, key: str, value: ArtefactSet) -> None:
        """Insert or update a cache entry, evicting LRU when full.

        Args:
            key: Cache key.
            value: Artefact set to store.
        """
        if key in self._entries:
            self._entries.move_to_end(key)
            self._entries[key] = value
            return
        self._entries[key] = value
        if len(self._entries) > self._max_size:
            self._entries.popitem(last=False)

    def invalidate(self, key: str) -> None:
        """Remove a cache entry if present.

        Args:
            key: Cache key to invalidate.
        """
        self._entries.pop(key, None)

    def clear(self) -> None:
        """Remove all cache entries."""
        self._entries.clear()

    @property
    def size(self) -> int:
        """Return the current number of cached entries."""
        return len(self._entries)
