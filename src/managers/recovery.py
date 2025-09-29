# managers/recovery.py
"""
ErrorRecoveryManager: tracks error frequency and performs recovery actions when threshold exceeded.
"""
import os
import json
import logging
import traceback

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import QMessageBox

import config


class ErrorRecoveryManager:
    """Monitors error occurrences and triggers recovery."""
    def __init__(self, parent, save_state: callable, reset_callback: callable):
        self.parent = parent
        self.save_state = save_state
        self.reset_callback = reset_callback
        self.error_count = 0
        self.last_error_time = QDateTime.currentDateTime()

    def handle_error(self, error: Exception, context: str) -> None:
        now = QDateTime.currentDateTime()
        if self.last_error_time.secsTo(now) > config.ERROR_WINDOW_SECONDS:
            self.error_count = 0
        self.error_count += 1
        self.last_error_time = now
        logging.error("Error in %s: %s", context, traceback.format_exc())

        if self.error_count >= config.ERROR_THRESHOLD:
            self._recover()

    def _recover(self) -> None:
        try:
            state = self.save_state()
            # Prefer parent's autosave manager path if available; fallback to config
            autosave_mgr = getattr(self.parent, 'autosave', None)
            path = getattr(autosave_mgr, 'path', config.AUTOSAVE_PATH)
            fname = f"recovery_{QDateTime.currentDateTime().toString(config.AUTOSAVE_TIMESTAMP_FORMAT)}.json"
            full = os.path.join(path, fname)
            with open(full, 'w', encoding='utf-8') as f:
                json.dump(state, f)

            self.reset_callback()
            logging.info("Recovery: state saved and application reset.")
            QMessageBox.warning(
                self.parent,
                "Recovery Action",
                "Multiple errors occurred. State saved and application reset."
            )
            self.error_count = 0

        except Exception as e:
            logging.critical("Recovery failed: %s", e)
            QMessageBox.critical(
                self.parent,
                "Critical Error",
                "Recovery failed. Please restart the application."
            )
