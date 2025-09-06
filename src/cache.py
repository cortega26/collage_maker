"""Thread-safe LRU cache used for image pixmaps and metadata.

This module previously contained multiple unrelated prototypes which have
been removed for clarity.  The cache is now implemented using
``collections.OrderedDict`` for efficient LRU eviction and uses a lock to
ensure thread safety.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Any, Optional, Tuple


class ImageCache:
    """A simple thread-safe LRU cache."""

    def __init__(self, max_size: int = 50, cleanup_threshold: float = 0.8) -> None:
        self.max_size = max_size
        self.cleanup_threshold = cleanup_threshold
        self._cache: "OrderedDict[str, Tuple[Any, dict]]" = OrderedDict()
        self._lock = RLock()

    def get(self, key: str) -> Tuple[Optional[Any], Optional[dict]]:
        """Retrieve *key* from the cache.

        Returns a tuple ``(pixmap, metadata)`` or ``(None, None)`` if the
        key is absent.  Accessing an item moves it to the end to mark it as
        most recently used.
        """
        with self._lock:
            try:
                value = self._cache.pop(key)
            except KeyError:
                return None, None
            self._cache[key] = value  # re-insert as most recent
            return value

    def put(self, key: str, pixmap: Any, metadata: dict) -> None:
        """Insert *key* into the cache.

        When the cache grows beyond ``max_size * cleanup_threshold`` a cleanup
        pass removes the least recently used entries.
        """
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            elif len(self._cache) >= self.max_size * self.cleanup_threshold:
                self._cleanup()
            self._cache[key] = (pixmap, metadata)

    def _cleanup(self) -> None:
        """Remove the oldest entries until the cache is at half capacity."""
        target = max(self.max_size // 2, 1)
        while len(self._cache) > target:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._cache.clear()


# Global cache instance used throughout the application
image_cache = ImageCache()

__all__ = ["ImageCache", "image_cache"]
