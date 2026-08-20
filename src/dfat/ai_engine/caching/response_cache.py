"""LLM response caching for reproducibility and reduced redundant API calls."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.llm.client import LLMResponse
from dfat.api.schemas.base import API_JSON_ENCODERS

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS: int = 3600


class CachedResponse(BaseModel):
    """A cached LLM response with metadata."""

    model_config = ConfigDict(frozen=False)

    response: LLMResponse
    cached_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cache_key: str
    hit_count: int = 0


class CacheStats(BaseModel):
    """Aggregate cache performance statistics."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    total_hits: int = 0
    total_misses: int = 0
    hit_rate: float = 0.0
    current_size: int = 0
    max_size: int = 0
    evictions: int = 0


class AIResponseCache:
    """LRU + TTL cache for ``LLMResponse`` keyed by prompt/model/temperature.

    Cache keys include the model name, temperature, and a SHA-256 hash of the
    prompt. Default TTL is one hour (``DEFAULT_TTL_SECONDS``).

    Thread-safe for asyncio concurrent access via ``asyncio.Lock``.
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Initialise the cache.

        Args:
            max_size: Maximum number of entries (LRU eviction when exceeded).
            ttl_seconds: Time-to-live for entries in seconds (default 1 hour).
        """
        self._max_size = max(1, max_size)
        self._ttl_seconds = max(0, ttl_seconds)
        self._store: OrderedDict[str, CachedResponse] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    @property
    def ttl_seconds(self) -> int:
        """Return the configured entry TTL in seconds."""
        return self._ttl_seconds

    def prompt_hash(self, prompt: str) -> str:
        """Return the SHA-256 digest of ``prompt`` used in cache keys."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _compute_cache_key(
        self,
        prompt: str,
        model: str,
        temperature: float,
    ) -> str:
        """Return SHA-256 of ``model | temperature | prompt_hash``.

        The key includes model name, temperature, and a prompt hash so identical
        forensic prompts reuse completions without mixing model settings.
        """
        payload = f"{model}|{temperature:.6f}|{self.prompt_hash(prompt)}"
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

    async def evict_expired(self) -> int:
        """Remove TTL-expired entries and return the number evicted."""
        async with self._lock:
            expired_keys = [
                key for key, entry in self._store.items() if self._is_expired(entry)
            ]
            for key in expired_keys:
                del self._store[key]
            return len(expired_keys)

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

    def common_prompt_patterns(self) -> list[str]:
        """Return rendered templates used for cache warming.

        Patterns cover classification, ranking, and summary prompts with a
        stable warmup artefact so repeated local-LLM calls can hit immediately.
        """
        from dfat.ai_engine.llm.prompts import ForensicPromptTemplates

        templates = ForensicPromptTemplates()
        warmup_line = (
            "[art-warmup] filesystem_metadata | path=/tmp/warmup "
            "suspicion_level=informational"
        )
        return [
            templates.render("classification", artefact_text=warmup_line),
            templates.render("ranking", artefact_text=warmup_line),
            templates.render(
                "summary",
                artefact_text=warmup_line,
                total_count=1,
                critical_count=0,
                high_count=0,
                categories="filesystem_metadata",
            ),
        ]

    async def warm(
        self,
        prompt: str,
        model: str,
        temperature: float,
        response: LLMResponse,
    ) -> None:
        """Insert a pre-computed response for a known prompt pattern."""
        await self.put(prompt, model, temperature, response)

    async def warm_common_patterns(
        self,
        model: str,
        temperature: float,
        generate: Optional[Callable[[str], Awaitable[LLMResponse]]] = None,
    ) -> int:
        """Pre-populate cache entries for common forensic prompt templates.

        When ``generate`` is supplied it is used to produce live completions.
        Otherwise a canned JSON/array placeholder is stored so later identical
        prompts are cache hits without a network round-trip.

        Args:
            model: Model name included in the cache key.
            temperature: Sampling temperature included in the cache key.
            generate: Optional async ``prompt -> LLMResponse`` producer.

        Returns:
            Number of patterns warmed.
        """
        warmed = 0
        for prompt in self.common_prompt_patterns():
            if generate is not None:
                response = await generate(prompt)
            else:
                response = LLMResponse(
                    text="[]",
                    model=model,
                    prompt_tokens=self._estimate_prompt_tokens(prompt),
                    completion_tokens=1,
                )
            await self.warm(prompt, model, temperature, response)
            warmed += 1
        logger.debug("Warmed %d common AI prompt patterns", warmed)
        return warmed

    @staticmethod
    def _estimate_prompt_tokens(prompt: str) -> int:
        """Estimate prompt tokens as ``len(text) / 4``."""
        if not prompt:
            return 0
        return max(1, (len(prompt) + 3) // 4)
