# === Module: cache.py ===
"""
Thread-safe LRU cache for QPixmap objects.
"""
import threading
from typing import Optional, Tuple, Dict, List
from PySide6.QtGui import QPixmap

class ImageCache:
    def __init__(self, max_size: int = 50, cleanup_threshold: float = 0.8):
        self._cache: Dict[str, Tuple[QPixmap, dict]] = {}
        self._order: List[str] = []
        self.max_size = max_size
        self.cleanup_threshold = cleanup_threshold
        self._lock = threading.Lock()

    def get(self, key: str) -> Tuple[Optional[QPixmap], Optional[dict]]:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None, None
            # Move to most recently used
            self._order.remove(key)
            self._order.append(key)
            return entry

    def put(self, key: str, pixmap: QPixmap, metadata: dict) -> None:
        with self._lock:
            if key in self._cache:
                self._order.remove(key)
            elif len(self._cache) >= self.max_size * self.cleanup_threshold:
                self._cleanup()
            self._cache[key] = (pixmap, metadata)
            self._order.append(key)

    def _cleanup(self) -> None:
        # Evict oldest until size <= max_size/2
        target = max(self.max_size // 2, 1)
        while len(self._cache) > target:
            oldest = self._order.pop(0)
            del self._cache[oldest]

# Global instance
image_cache = ImageCache()