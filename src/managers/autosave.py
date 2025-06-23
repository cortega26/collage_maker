# managers/autosave.py
"""
AutosaveManager: periodically saves collage state to JSON and manages old file cleanup.
"""
import os
import glob
import json
import logging
from typing import Optional

from PySide6.QtCore import QTimer, QDateTime

import config


class AutosaveManager:
    """Handles periodic autosaving of application state."""
    def __init__(self, parent, save_callback: callable):
        self.parent = parent
        self.save_callback = save_callback
        self.timer = QTimer(parent)
        self.timer.timeout.connect(self.perform_autosave)
        self.timer.start(config.AUTOSAVE_INTERVAL_MS)
        self.path = config.AUTOSAVE_PATH
        os.makedirs(self.path, exist_ok=True)

    def perform_autosave(self) -> None:
        try:
            timestamp = QDateTime.currentDateTime().toString(config.AUTOSAVE_TIMESTAMP_FORMAT)
            fname = f"collage_autosave_{timestamp}.json"
            full = os.path.join(self.path, fname)
            state = self.save_callback()
            with open(full, 'w', encoding='utf-8') as f:
                json.dump(state, f)
            self._cleanup_old()
            logging.info("Autosaved state to %s", full)
        except Exception as e:
            logging.error("Autosave failed: %s", e)

    def _cleanup_old(self) -> None:
        pattern = os.path.join(self.path, "collage_autosave_*.json")
        files = sorted(glob.glob(pattern), key=os.path.getctime, reverse=True)
        for old in files[config.MAX_AUTOSAVE_FILES:]:
            try:
                os.remove(old)
            except Exception:
                pass

    def get_latest(self) -> Optional[str]:
        pattern = os.path.join(self.path, "collage_autosave_*.json")
        files = glob.glob(pattern)
        if not files:
            return None
        return max(files, key=os.path.getctime)
