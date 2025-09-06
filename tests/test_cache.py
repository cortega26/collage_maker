import os
import sys
import threading

# Ensure project root is on the path when tests are executed from the tests directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.cache import ImageCache


def test_lru_eviction_order():
    cache = ImageCache(max_size=2, cleanup_threshold=1.0)
    cache.put('a', 'A', {})
    cache.put('b', 'B', {})
    # Access 'a' to make it most recently used
    cache.get('a')
    cache.put('c', 'C', {})  # Should evict 'b'
    assert cache.get('b') == (None, None)
    assert cache.get('a')[0] == 'A'
    assert cache.get('c')[0] == 'C'


def test_thread_safety():
    cache = ImageCache(max_size=10)

    def worker(start):
        for i in range(start, start + 5):
            cache.put(str(i), i, {})
            cache.get(str(i))

    threads = [threading.Thread(target=worker, args=(n * 5,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # After operations the cache should not exceed max_size
    assert len(cache._cache) <= cache.max_size
