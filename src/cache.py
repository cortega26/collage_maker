"""Thread-safe LRU cache used for image pixmaps and metadata.

This module previously contained multiple unrelated prototypes which have
been removed for clarity.  The cache is now implemented using
``collections.OrderedDict`` for efficient LRU eviction and uses a lock to
ensure thread safety.

The June 2024 quality audit highlighted that the module exposed a single
global cache instance, which made it difficult to swap cache strategies
in tests or future worker implementations.  The module now exposes
factory and context-manager helpers so callers can override the default
cache without modifying import order or relying on global state.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from threading import RLock
from typing import Any, Callable, Iterator, Optional, Tuple


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

    # Public wrapper to avoid using a private method from callers
    def cleanup(self) -> None:
        """Evict least-recently-used entries down to half capacity."""
        with self._lock:
            self._cleanup()


_cache_factory: Callable[[], ImageCache]
_cache_instance: Optional[ImageCache]
_cache_factory_lock = RLock()


def _default_cache_factory() -> ImageCache:
    """Return a new :class:`ImageCache` using default configuration."""

    return ImageCache()


_cache_factory = _default_cache_factory
_cache_instance = None


def configure_cache(factory: Callable[[], ImageCache], *, reset: bool = True) -> None:
    """Configure the cache factory used to lazily supply ``ImageCache`` instances.

    Parameters
    ----------
    factory:
        A callable returning a fully configured :class:`ImageCache` instance.
        The callable is invoked lazily when :func:`get_cache` is called.
    reset:
        When ``True`` (default) the current cache instance is discarded so the
        next :func:`get_cache` call yields a fresh instance from ``factory``.
    """

    if not callable(factory):  # pragma: no cover - defensive programming
        raise TypeError("factory must be callable")

    with _cache_factory_lock:
        global _cache_factory, _cache_instance
        _cache_factory = factory
        if reset:
            _cache_instance = None


def get_cache() -> ImageCache:
    """Return the lazily constructed cache instance."""

    with _cache_factory_lock:
        global _cache_instance
        if _cache_instance is None:
            _cache_instance = _cache_factory()
        return _cache_instance


@contextmanager
def override_cache(cache: ImageCache) -> Iterator[ImageCache]:
    """Temporarily replace the active cache instance within a ``with`` block.

    Examples
    --------
    ``override_cache`` is primarily intended for tests which need a clean cache
    configuration:

    >>> with override_cache(ImageCache(max_size=1)) as temporary:
    ...     assert get_cache() is temporary
    ...
    >>> assert get_cache() is not temporary
    """

    with _cache_factory_lock:
        global _cache_factory, _cache_instance
        previous_factory = _cache_factory
        previous_instance = _cache_instance
        def _factory() -> ImageCache:
            return cache

        _cache_factory = _factory
        _cache_instance = cache
    try:
        yield cache
    finally:
        with _cache_factory_lock:
            _cache_factory = previous_factory
            _cache_instance = previous_instance


class _ImageCacheProxy:
    """Proxy that forwards attribute access to :func:`get_cache`.

    This preserves the long-standing ``image_cache`` import style while allowing
    dependency injection through :func:`configure_cache` and
    :func:`override_cache`.
    """

    def __getattr__(self, item: str) -> Any:
        return getattr(get_cache(), item)

    def __repr__(self) -> str:  # pragma: no cover - trivial representation
        return repr(get_cache())


# Global proxy used throughout the application for backward compatibility
image_cache = _ImageCacheProxy()

__all__ = [
    "ImageCache",
    "configure_cache",
    "get_cache",
    "image_cache",
    "override_cache",
]
