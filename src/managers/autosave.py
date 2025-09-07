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
import time
import uuid
from collections import Counter
from typing import Optional

from PySide6.QtCore import QDateTime, QTimer

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


class AutosaveManager:
    """Handles periodic autosaving of application state."""

    def __init__(self, parent, save_callback: callable, timer: Optional[QTimer] = None):
        self.parent = parent
        self.save_callback = save_callback
        self.timer = timer or QTimer(parent)
        self.timer.timeout.connect(self.perform_autosave)
        self.timer.start(config.AUTOSAVE_INTERVAL_MS)
        self.path = config.AUTOSAVE_PATH
        os.makedirs(self.path, exist_ok=True)

    def perform_autosave(self) -> None:
        """Persist current state to disk with retries and structured logs."""
        cid = uuid.uuid4().hex
        log = logging.LoggerAdapter(logging.getLogger(__name__), {"cid": cid})
        timestamp = QDateTime.currentDateTime().toString(config.AUTOSAVE_TIMESTAMP_FORMAT)
        fname = f"collage_autosave_{timestamp}.json"
        full = os.path.join(self.path, fname)
        retries = 3
        backoff = 0.1
        start = time.perf_counter()
        for attempt in range(1, retries + 1):
            try:
                state = self.save_callback()
                with open(full, "w", encoding="utf-8") as f:
                    json.dump(state, f)
                self._cleanup_old(log)
                duration = (time.perf_counter() - start) * 1000
                autosave_metrics.record("success", duration)
                log.info("autosave complete", extra={"path": full, "duration_ms": duration})
                return
            except Exception as exc:  # pragma: no cover - caught and reraised
                log.warning(
                    "autosave attempt failed",  # Runbook: check disk space, permissions
                    extra={"attempt": attempt, "path": full, "error": str(exc)},
                )
                if attempt == retries:
                    autosave_metrics.record("failure")
                    log.error(
                        "autosave failed after retries",  # Runbook: see storage troubleshooting
                        extra={"path": full, "error": str(exc)},
                    )
                    raise AutosaveError(f"Failed to autosave to {full}") from exc
                time.sleep(backoff)
                backoff *= 2

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
