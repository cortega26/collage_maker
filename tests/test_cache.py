"""Tests for the configurable image cache factory."""
from __future__ import annotations

import threading

import pytest

from src.cache import ImageCache, configure_cache, get_cache, override_cache


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    """Ensure each test starts with the default cache factory."""

    configure_cache(ImageCache)
    yield
    configure_cache(ImageCache)


def test_configure_cache_allows_custom_factory() -> None:
    """A custom factory should be invoked lazily and configure cache limits."""

    configure_cache(lambda: ImageCache(max_size=1))
    cache = get_cache()
    assert isinstance(cache, ImageCache)
    assert cache.max_size == 1


def test_override_cache_temporarily_swaps_instance() -> None:
    """The override context should swap caches and restore the prior instance."""

    original = get_cache()
    replacement = ImageCache(max_size=2)
    with override_cache(replacement) as cache:
        assert cache is replacement
        assert get_cache() is replacement
    restored = get_cache()
    assert restored is not replacement
    assert isinstance(restored, ImageCache)
    assert restored.max_size == original.max_size


def test_lru_eviction_order() -> None:
    """Direct cache instances should continue to evict the least recently used."""

    cache = ImageCache(max_size=2, cleanup_threshold=1.0)
    cache.put("a", "A", {})
    cache.put("b", "B", {})
    cache.get("a")
    cache.put("c", "C", {})

    assert cache.get("b") == (None, None)
    assert cache.get("a")[0] == "A"
    assert cache.get("c")[0] == "C"


def test_thread_safety() -> None:
    """Cache operations across threads should remain bounded by ``max_size``."""

    cache = ImageCache(max_size=10)

    def worker(start: int) -> None:
        for i in range(start, start + 5):
            cache.put(str(i), i, {})
            cache.get(str(i))

    threads = [threading.Thread(target=worker, args=(n * 5,)) for n in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(cache._cache) <= cache.max_size
