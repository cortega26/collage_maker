# managers/autosave.py
"""Autosave manager with structured logging and metrics.

This module now exposes :class:`AutosaveManager` which periodically saves
collage state to JSON.  Errors surface as :class:`AutosaveError` with rich
context and retries with exponential backoff.  All operations emit
structured logs including a correlation identifier (``cid``) so that issues
can be traced across systems.  Basic metrics are recorded via the
``autosave_metrics`` instance which tracks success and failure counts as well
as observed durations.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import (
    QCoreApplication,
    QDateTime,
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    Signal,
)

from .. import config


class AutosaveError(RuntimeError):
    """Raised when an autosave operation ultimately fails."""


class _AutosaveMetrics:
    """Simple in-memory metrics collector."""

    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self.durations: list[float] = []

    def record(self, name: str, duration: float | None = None) -> None:
        self.counters[name] += 1
        if duration is not None:
            self.durations.append(duration)


autosave_metrics = _AutosaveMetrics()


@dataclass(slots=True)
class _AutosaveContext:
    """Holds state shared across autosave attempts."""

    cid: str
    path: str
    log: logging.LoggerAdapter


class _AutosaveSignals(QObject):
    """Signals exposed by :class:`_AutosaveWorker`."""

    finished = Signal()
    error = Signal(str)
    result = Signal(str)


class _AutosaveWorker(QRunnable):
    """Minimal QRunnable wrapper for background autosave writes."""

    def __init__(self, fn: Callable[[], str]):
        super().__init__()
        self._fn = fn
        self.signals = _AutosaveSignals()

    def run(self) -> None:  # pragma: no cover - exercised via Qt signal wiring
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - propagate error detail via signal
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class AutosaveManager:
    """Handles periodic autosaving of application state."""

    def __init__(
        self,
        parent,
        save_callback: callable,
        timer: Optional[QTimer] = None,
        retry_scheduler: Optional[Callable[[int, Callable[[], None]], None]] = None,
    ):
        self.parent = parent
        self.save_callback = save_callback
        self.timer = timer or QTimer(parent)
        self.timer.timeout.connect(self.perform_autosave)
        self.timer.start(config.AUTOSAVE_INTERVAL_MS)
        self.path = config.AUTOSAVE_PATH
        os.makedirs(self.path, exist_ok=True)

        self._thread_pool = QThreadPool.globalInstance()
        self._max_retries = 3
        self._initial_backoff_ms = 100
        self._is_running = False
        self._retry_scheduled = False
        self._pending_exception: AutosaveError | None = None
        self._idle_event = threading.Event()
        self._idle_event.set()
        self._retry_scheduler = retry_scheduler or (
            lambda ms, cb: QTimer.singleShot(ms, cb)
        )

    def wait_for_idle(self, timeout: float | None = None) -> None:
        """Block until the current autosave (if any) completes.

        Primarily used in tests to synchronise with background workers.
        """

        app = QCoreApplication.instance()
        deadline = None if timeout is None else time.perf_counter() + timeout
        step = 0.01 if app is not None else timeout
        while True:
            if self._idle_event.wait(0 if app is None else step):
                break
            if app is not None:
                app.processEvents()
            if deadline is not None and time.perf_counter() >= deadline:
                raise TimeoutError("Autosave task did not complete in time")
        if self._pending_exception is not None:
            exc = self._pending_exception
            self._pending_exception = None
            raise exc

    def perform_autosave(self) -> None:
        """Persist current state to disk with retries and structured logs."""

        if self._is_running or self._retry_scheduled:
            return

        cid = uuid.uuid4().hex
        log = logging.LoggerAdapter(logging.getLogger(__name__), {"cid": cid})
        timestamp = QDateTime.currentDateTime().toString(config.AUTOSAVE_TIMESTAMP_FORMAT)
        fname = f"collage_autosave_{timestamp}.json"
        full = os.path.join(self.path, fname)
        context = _AutosaveContext(cid=cid, path=full, log=log)
        self._start_attempt(context, attempt=1, backoff_ms=self._initial_backoff_ms)

    def _start_attempt(
        self,
        context: _AutosaveContext,
        *,
        attempt: int,
        backoff_ms: int,
    ) -> None:
        self._is_running = True
        self._idle_event.clear()

        start = time.perf_counter()
        try:
            state = self.save_callback()
        except Exception as exc:  # pragma: no cover - propagated to caller
            self._finalize_failure(context, attempt, str(exc), terminal=True)
            raise AutosaveError(f"Failed to autosave to {context.path}") from exc

        def _write_payload() -> str:
            with open(context.path, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
            return context.path

        worker = _AutosaveWorker(_write_payload)

        def _on_success(_: str) -> None:
            duration = (time.perf_counter() - start) * 1000
            autosave_metrics.record("success", duration)
            context.log.info(
                "autosave complete",
                extra={"path": context.path, "duration_ms": duration},
            )
            self._cleanup_old(context.log)
            self._pending_exception = None

        def _on_error(message: str) -> None:
            self._handle_worker_error(
                context,
                attempt=attempt,
                backoff_ms=backoff_ms,
                start=start,
                error_message=message,
            )

        worker.signals.result.connect(_on_success)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(self._mark_idle)

        self._thread_pool.start(worker)

    def _mark_idle(self) -> None:
        if not self._retry_scheduled:
            self._is_running = False
            self._idle_event.set()


    def _cleanup_old(self, log: Optional[logging.LoggerAdapter] = None) -> None:
        pattern = os.path.join(self.path, "collage_autosave_*.json")
        files = sorted(glob.glob(pattern), key=os.path.getctime, reverse=True)
        for old in files[config.MAX_AUTOSAVE_FILES:]:
            try:
                os.remove(old)
            except OSError as exc:
                (log or logging.getLogger(__name__)).warning(
                    "cleanup failed",  # Runbook: verify file permissions
                    extra={"file": old, "error": str(exc)},
                )

    def get_latest(self) -> Optional[str]:
        pattern = os.path.join(self.path, "collage_autosave_*.json")
        files = glob.glob(pattern)
        if not files:
            return None
        return max(files, key=os.path.getctime)

    def _handle_worker_error(
        self,
        context: _AutosaveContext,
        *,
        attempt: int,
        backoff_ms: int,
        start: float,
        error_message: str,
    ) -> None:
        context.log.warning(
            "autosave attempt failed",
            extra={
                "attempt": attempt,
                "path": context.path,
                "error": error_message,
            },
        )

        if attempt >= self._max_retries:
            self._finalize_failure(context, attempt, error_message, terminal=True)
            return

        self._retry_scheduled = True

        def _retry() -> None:
            self._retry_scheduled = False
            self._start_attempt(
                context,
                attempt=attempt + 1,
                backoff_ms=int(min(backoff_ms * 2, 2000)),
            )

        # Account for time spent attempting already when computing duration.
        autosave_metrics.record(
            "retry",
            (time.perf_counter() - start) * 1000,
        )

        self._retry_scheduler(backoff_ms, _retry)

    def _finalize_failure(
        self,
        context: _AutosaveContext,
        attempt: int,
        error_message: str,
        *,
        terminal: bool,
    ) -> None:
        autosave_metrics.record("failure")
        context.log.error(
            "autosave failed after retries" if terminal else "autosave failed",
            extra={"attempt": attempt, "path": context.path, "error": error_message},
        )
        self._pending_exception = AutosaveError(
            f"Failed to autosave to {context.path}: {error_message}"
        )
        self._is_running = False
        self._retry_scheduled = False
        self._idle_event.set()
