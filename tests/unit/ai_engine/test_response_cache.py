"""Unit tests for AI response caching (Prompt 5.16)."""

from __future__ import annotations

import asyncio

import pytest

from dfat.ai_engine.caching import AIResponseCache
from dfat.ai_engine.llm.client import LLMResponse


def _response(text: str = "ok") -> LLMResponse:
    return LLMResponse(text=text, model="llama3", prompt_tokens=1, completion_tokens=1)


@pytest.mark.asyncio
async def test_identical_prompts_produce_cache_hits() -> None:
    cache = AIResponseCache(max_size=10, ttl_seconds=3600)
    await cache.put("prompt-a", "llama3", 0.1, _response("answer"))

    first = await cache.get("prompt-a", "llama3", 0.1)
    second = await cache.get("prompt-a", "llama3", 0.1)

    assert first is not None and second is not None
    assert first.response.text == "answer"
    assert second.hit_count >= 2
    stats = await cache.get_stats()
    assert stats.total_hits == 2
    assert stats.total_misses == 0
    assert stats.hit_rate == 1.0


@pytest.mark.asyncio
async def test_different_temperatures_produce_cache_misses() -> None:
    cache = AIResponseCache()
    await cache.put("prompt-a", "llama3", 0.1, _response())

    hit = await cache.get("prompt-a", "llama3", 0.1)
    miss = await cache.get("prompt-a", "llama3", 0.2)

    assert hit is not None
    assert miss is None
    stats = await cache.get_stats()
    assert stats.total_hits == 1
    assert stats.total_misses == 1


@pytest.mark.asyncio
async def test_lru_eviction_works() -> None:
    cache = AIResponseCache(max_size=2, ttl_seconds=3600)
    await cache.put("p1", "llama3", 0.1, _response("1"))
    await cache.put("p2", "llama3", 0.1, _response("2"))
    # Access p1 so p2 is least recently used
    assert await cache.get("p1", "llama3", 0.1) is not None
    await cache.put("p3", "llama3", 0.1, _response("3"))

    assert await cache.get("p2", "llama3", 0.1) is None  # evicted
    assert await cache.get("p1", "llama3", 0.1) is not None
    assert await cache.get("p3", "llama3", 0.1) is not None
    stats = await cache.get_stats()
    assert stats.evictions == 1
    assert stats.current_size == 2


@pytest.mark.asyncio
async def test_stats_and_invalidate_all() -> None:
    cache = AIResponseCache(max_size=5)
    await cache.put("a", "llama3", 0.1, _response())
    await cache.get("a", "llama3", 0.1)
    await cache.get("missing", "llama3", 0.1)
    cleared = await cache.invalidate_all()
    assert cleared == 1
    stats = await cache.get_stats()
    assert stats.current_size == 0
    assert stats.max_size == 5


@pytest.mark.asyncio
async def test_cache_is_concurrent_safe() -> None:
    cache = AIResponseCache(max_size=50, ttl_seconds=3600)

    async def writer(i: int) -> None:
        await cache.put(f"prompt-{i}", "llama3", 0.1, _response(str(i)))

    async def reader(i: int) -> None:
        await cache.get(f"prompt-{i % 10}", "llama3", 0.1)

    await asyncio.gather(*(writer(i) for i in range(20)))
    await asyncio.gather(*(reader(i) for i in range(40)))
    stats = await cache.get_stats()
    assert stats.current_size <= 50
    assert stats.total_hits + stats.total_misses == 40


def test_compute_cache_key_deterministic() -> None:
    cache = AIResponseCache()
    a = cache._compute_cache_key("hello", "llama3", 0.1)
    b = cache._compute_cache_key("hello", "llama3", 0.1)
    c = cache._compute_cache_key("hello", "llama3", 0.2)
    assert a == b
    assert a != c
    assert len(a) == 64
    assert cache.ttl_seconds == 3600
    prompt_digest = cache.prompt_hash("hello")
    assert len(prompt_digest) == 64
    different_model = cache._compute_cache_key("hello", "mistral", 0.1)
    different_prompt = cache._compute_cache_key("other", "llama3", 0.1)
    assert a != different_model
    assert a != different_prompt


@pytest.mark.asyncio
async def test_warm_common_patterns_are_cache_hits() -> None:
    cache = AIResponseCache(ttl_seconds=3600)
    warmed = await cache.warm_common_patterns("llama3", 0.1)
    assert warmed == 3
    for prompt in cache.common_prompt_patterns():
        hit = await cache.get(prompt, "llama3", 0.1)
        assert hit is not None
        assert hit.response.text == "[]"
