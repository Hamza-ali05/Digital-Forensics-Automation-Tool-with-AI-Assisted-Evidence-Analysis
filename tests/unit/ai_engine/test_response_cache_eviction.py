"""Unit tests for AIResponseCache eviction helper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dfat.ai_engine.caching.response_cache import AIResponseCache, CachedResponse
from dfat.ai_engine.llm.client import LLMResponse


@pytest.mark.asyncio
async def test_evict_expired_removes_stale_entries() -> None:
    cache = AIResponseCache(max_size=10, ttl_seconds=60)
    stale = CachedResponse(
        response=LLMResponse(text="old", model="m", prompt_tokens=1, completion_tokens=1),
        cached_at=datetime.now(UTC) - timedelta(seconds=120),
        cache_key="stale-key",
    )
    fresh = CachedResponse(
        response=LLMResponse(text="new", model="m", prompt_tokens=1, completion_tokens=1),
        cached_at=datetime.now(UTC),
        cache_key="fresh-key",
    )
    cache._store["stale-key"] = stale
    cache._store["fresh-key"] = fresh

    removed = await cache.evict_expired()

    assert removed == 1
    assert "stale-key" not in cache._store
    assert "fresh-key" in cache._store
