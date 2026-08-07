"""LLM response caching for reproducibility and reduced redundant API calls."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.llm.client import LLMResponse

logger = logging.getLogger(__name__)


class CachedResponse(BaseModel):
    """A cached LLM response with metadata."""

    model_config = ConfigDict(frozen=False)

    response: LLMResponse
    cached_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cache_key: str
    hit_count: int = 0


class CacheStats(BaseModel):
    """Aggregate cache performance statistics."""

    model_config = ConfigDict(frozen=False)

    total_hits: int = 0
    total_misses: int = 0
    hit_rate: float = 0.0
    current_size: int = 0
    max_size: int = 0
    evictions: int = 0


class AIResponseCache:
    """LRU + TTL cache for ``LLMResponse`` keyed by prompt/model/temperature.

    Thread-safe for asyncio concurrent access via ``asyncio.Lock``.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600) -> None:
        """Initialise the cache.

        Args:
            max_size: Maximum number of entries (LRU eviction when exceeded).
            ttl_seconds: Time-to-live for entries in seconds.
        """
        self._max_size = max(1, max_size)
        self._ttl_seconds = max(0, ttl_seconds)
        self._store: OrderedDict[str, CachedResponse] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _compute_cache_key(
        self,
        prompt: str,
        model: str,
        temperature: float,
    ) -> str:
        """Return SHA-256 of ``prompt + model + str(temperature)``."""
        payload = f"{prompt}{model}{temperature!s}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def get(
        self,
        prompt: str,
        model: str,
        temperature: float,
    ) -> Optional[CachedResponse]:
        """Return a cached response for identical inputs, or ``None``.

        Updates LRU order and hit count on success. Expired entries miss.
        """
        key = self._compute_cache_key(prompt, model, temperature)
        async with self._lock:
            cached = self._store.get(key)
            if cached is None:
                self._misses += 1
                return None
            if self._is_expired(cached):
                del self._store[key]
                self._misses += 1
                logger.debug("AIResponseCache TTL miss for key=%s…", key[:12])
                return None
            cached.hit_count += 1
            self._store.move_to_end(key)
            self._hits += 1
            return cached

    async def put(
        self,
        prompt: str,
        model: str,
        temperature: float,
        response: LLMResponse,
    ) -> None:
        """Store an LLM response under the computed cache key."""
        key = self._compute_cache_key(prompt, model, temperature)
        entry = CachedResponse(
            response=response,
            cached_at=datetime.now(UTC),
            cache_key=key,
            hit_count=0,
        )
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = entry
                return
            while len(self._store) >= self._max_size:
                self._store.popitem(last=False)
                self._evictions += 1
            self._store[key] = entry

    async def invalidate_all(self) -> int:
        """Clear the entire cache and return the number of entries removed."""
        async with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    async def get_stats(self) -> CacheStats:
        """Return hit/miss/eviction statistics and current size."""
        async with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total) if total else 0.0
            return CacheStats(
                total_hits=self._hits,
                total_misses=self._misses,
                hit_rate=round(hit_rate, 4),
                current_size=len(self._store),
                max_size=self._max_size,
                evictions=self._evictions,
            )

    def _is_expired(self, cached: CachedResponse) -> bool:
        """Return True when the entry exceeds the configured TTL."""
        if self._ttl_seconds <= 0:
            return False
        age = (datetime.now(UTC) - cached.cached_at).total_seconds()
        return age > self._ttl_seconds
