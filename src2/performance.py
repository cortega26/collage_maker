# === Module: performance.py ===
"""
Memory and resource monitoring.
"""
import gc
from cache import image_cache
import logging
try: import psutil; HAS_PSUTIL=True
except ImportError: HAS_PSUTIL=False

class PerformanceMonitor:
    def __init__(self, threshold=500*1024*1024, interval=300):
        self.threshold=threshold; self.interval=interval
        self.last=0
    def check(self):
        if not HAS_PSUTIL: return
        mem=psutil.Process().memory_info().rss
        if mem>self.threshold:
            gc.collect(); image_cache._cleanup(); logging.info("Memory optimized")
