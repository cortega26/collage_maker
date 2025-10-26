"""Background encoding helpers for autosave payloads."""
from __future__ import annotations

import base64
import logging
from threading import Lock
from typing import Callable, Dict, Optional, Tuple

from PySide6.QtCore import QBuffer, QIODevice, QThreadPool
from PySide6.QtGui import QImage

from ..workers import Worker

LOGGER = logging.getLogger(__name__)

AutosaveToken = Tuple[int, int]


def _encode_image(image: QImage) -> Optional[str]:
    """Serialize a QImage into a base64 encoded PNG string."""
    if image.isNull():
        return None
    buffer = QBuffer()
    if not buffer.open(QIODevice.WriteOnly):
        raise RuntimeError("Unable to open buffer for autosave encoding")
    try:
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Failed to save image for autosave encoding")
        return base64.b64encode(bytes(buffer.data())).decode("ascii")
    finally:
        buffer.close()


class AutosaveEncodingManager:
    """Coordinates background encoding tasks for autosave payloads."""

    def __init__(self) -> None:
        self._pool = QThreadPool.globalInstance()
        self._lock = Lock()
        self._pending: Dict[AutosaveToken, bool] = {}

    def encode(
        self,
        token: AutosaveToken,
        image: QImage,
        callback: Callable[[AutosaveToken, Optional[str]], None],
    ) -> None:
        """Encode ``image`` asynchronously and forward the payload to ``callback``."""
        with self._lock:
            self._pending[token] = True
        worker = Worker(_encode_image, image.copy())

        def _handle_result(payload: Optional[str], *, expected: AutosaveToken = token) -> None:
            self._finish(expected)
            callback(expected, payload)

        def _handle_error(message: str, *, expected: AutosaveToken = token) -> None:
            LOGGER.error("Autosave encoding failed: %s", message)
            self._finish(expected)
            callback(expected, None)

        worker.signals.result.connect(_handle_result)
        worker.signals.error.connect(_handle_error)
        self._pool.start(worker)

    def _finish(self, token: AutosaveToken) -> None:
        with self._lock:
            self._pending.pop(token, None)

    def has_pending(self, token: AutosaveToken) -> bool:
        """Return whether an encoding task is outstanding for ``token``."""
        with self._lock:
            return self._pending.get(token, False)


_ENCODER: Optional[AutosaveEncodingManager] = None


def get_autosave_encoder() -> AutosaveEncodingManager:
    """Return the shared :class:`AutosaveEncodingManager` instance."""
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = AutosaveEncodingManager()
    return _ENCODER
