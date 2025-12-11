# managers/performance.py
"""
PerformanceMonitor: checks memory usage and triggers cleanup when thresholds exceeded.
"""
import gc
import logging

from PySide6.QtCore import QTimer, QDateTime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from .. import config
from ..cache import get_cache


class PerformanceMonitor:
    """Monitors memory usage and performs cleanup actions."""
    def __init__(self, parent):
        self.parent = parent
        self.timer = QTimer(parent)
        self.timer.timeout.connect(self.check_memory)
        self.timer.start(config.MEMORY_CLEANUP_INTERVAL_SECS * 1000)
        self.last_cleanup = QDateTime.currentDateTime()

    def check_memory(self) -> None:
        if not HAS_PSUTIL:
            return
        try:
            proc = psutil.Process()
            mem = proc.memory_info().rss
            if mem > config.MEMORY_THRESHOLD_BYTES:
                now = QDateTime.currentDateTime()
                if self.last_cleanup.secsTo(now) >= config.MEMORY_CLEANUP_INTERVAL_SECS:
                    self._optimize()
                    self.last_cleanup = now
        except Exception as e:
            logging.warning("Memory check failed: %s", e)

    def _optimize(self) -> None:
        get_cache().cleanup()
        # Attempt to optimize grid cells if accessible
        if hasattr(self.parent, "collage") and hasattr(self.parent.collage, "optimize_memory"):
            self.parent.collage.optimize_memory()
        elif hasattr(self.parent, "optimize_memory"):
             self.parent.optimize_memory()
            
        gc.collect()
        logging.info("PerformanceMonitor: memory optimization executed")
