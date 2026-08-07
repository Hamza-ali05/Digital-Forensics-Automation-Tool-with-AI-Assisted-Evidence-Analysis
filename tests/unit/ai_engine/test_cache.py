"""Unit tests for AI response cache (Prompt 5.20)."""

from __future__ import annotations

import pytest

from dfat.ai_engine.caching import AIResponseCache
from dfat.ai_engine.llm.client import LLMResponse


def _response(text: str = "ok") -> LLMResponse:
    return LLMResponse(text=text, model="llama3", prompt_tokens=1, completion_tokens=1)


@pytest.mark.asyncio
async def test_cache_hit_on_identical_input() -> None:
    """Verify identical prompt/model/temperature produce cache hits."""
    cache = AIResponseCache(max_size=10, ttl_seconds=3600)
    await cache.put("prompt-a", "llama3", 0.1, _response("answer"))
    first = await cache.get("prompt-a", "llama3", 0.1)
    second = await cache.get("prompt-a", "llama3", 0.1)
    assert first is not None and second is not None
    assert first.response.text == "answer"
    stats = await cache.get_stats()
    assert stats.total_hits == 2
    assert stats.hit_rate == 1.0


@pytest.mark.asyncio
async def test_cache_miss_on_different_temperature() -> None:
    """Verify temperature changes cause cache misses."""
    cache = AIResponseCache()
    await cache.put("prompt-a", "llama3", 0.1, _response())
    assert await cache.get("prompt-a", "llama3", 0.1) is not None
    assert await cache.get("prompt-a", "llama3", 0.2) is None


@pytest.mark.asyncio
async def test_lru_eviction() -> None:
    """Verify least-recently-used entries are evicted at capacity."""
    cache = AIResponseCache(max_size=2, ttl_seconds=3600)
    await cache.put("p1", "llama3", 0.1, _response("1"))
    await cache.put("p2", "llama3", 0.1, _response("2"))
    assert await cache.get("p1", "llama3", 0.1) is not None
    await cache.put("p3", "llama3", 0.1, _response("3"))
    assert await cache.get("p2", "llama3", 0.1) is None
    assert await cache.get("p1", "llama3", 0.1) is not None
    assert await cache.get("p3", "llama3", 0.1) is not None


@pytest.mark.asyncio
async def test_cache_stats_accuracy() -> None:
    """Verify hit/miss/eviction counters are accurate."""
    cache = AIResponseCache(max_size=5)
    await cache.put("a", "llama3", 0.1, _response())
    await cache.get("a", "llama3", 0.1)
    await cache.get("missing", "llama3", 0.1)
    stats = await cache.get_stats()
    assert stats.total_hits == 1
    assert stats.total_misses == 1
    assert stats.current_size == 1
    assert stats.max_size == 5
