# workers.py
"""
Background task execution utilities for Collage Maker.
Defines a unified Worker for QRunnable tasks, a TaskQueue, and batch processing support.
"""
import logging
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QRunnable, QThreadPool, QObject, Signal, QSize
from PySide6.QtWidgets import QProgressDialog, QMessageBox
from PySide6.QtGui import QImageReader, QPixmap

import config
from cache import image_cache
from optimizer import ImageOptimizer
from widgets.cell import CollageCell


class WorkerSignals(QObject):
    started = Signal()
    finished = Signal()
    error = Signal(str)
    progress = Signal(int)
    result = Signal(object)


class Worker(QRunnable):
    """Wraps any function to run in a QThreadPool."""
    def __init__(
        self,
        fn: Callable,
        *args,
        progress_callback: Optional[Callable[[int], Any]] = None,
        **kwargs
    ):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        if progress_callback:
            self.signals.progress.connect(progress_callback)

    def run(self) -> None:
        try:
            self.signals.started.emit()
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            logging.error("Worker error: %s", e)
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class TaskQueue:
    """Queued task manager with priority support."""
    def __init__(self, max_concurrent: int = 4):
        self._queue: List[tuple[int, Worker]] = []
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(max_concurrent)
        self._processing = False

    def add_task(self, worker: Worker, priority: int = 0) -> None:
        """Schedule a Worker with an optional priority."""
        self._queue.append((priority, worker))
        self._queue.sort(key=lambda x: x[0], reverse=True)
        if not self._processing:
            self._process_next()

    def _process_next(self) -> None:
        if not self._queue:
            self._processing = False
            return
        self._processing = True
        _, worker = self._queue.pop(0)
        worker.signals.finished.connect(self._process_next)
        self.thread_pool.start(worker)

    def clear(self) -> None:
        """Remove all scheduled tasks."""
        self._queue.clear()

    def is_empty(self) -> bool:
        return not bool(self._queue)


class BatchProcessor:
    """Handles batch loading and caching of image files."""
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.thread_pool = QThreadPool.globalInstance()

    def process_files(self, file_paths: List[str], target_size: Optional[QSize] = None) -> None:
        """Asynchronously load, optimize, cache images, showing progress."""
        dialog = QProgressDialog(
            "Processing images...", "Cancel", 0, len(file_paths), self.parent
        )
        dialog.setWindowModality(True)
        dialog.show()

        def _task(path_list):
            for idx, path in enumerate(path_list):
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                if target_size:
                    reader.setScaledSize(target_size)
                img = reader.read()
                if img.isNull():
                    logging.error("Batch load failed: %s", reader.errorString())
                    continue
                pix = QPixmap.fromImage(img)
                image_cache.put(path, pix, ImageOptimizer.process_metadata(path))
                progress = int((idx + 1) / len(path_list) * 100)
                yield progress

        # Wrap generator in a worker
        def run_batch():
            for p in _task(file_paths):
                batch_worker.signals.progress.emit(p)
            return True

        batch_worker = Worker(run_batch)
        batch_worker.signals.progress.connect(dialog.setValue)
        batch_worker.signals.error.connect(lambda msg: QMessageBox.warning(self.parent, "Batch Error", msg))
        batch_worker.signals.finished.connect(dialog.close)

        self.thread_pool.start(batch_worker)
