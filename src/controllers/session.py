"""Session controller for collage state management.

This module introduces :class:`CollageSessionController`, a small service
layer that mediates between UI widgets and persistence workflows.  It keeps
track of undo/redo stacks and exposes idempotent helpers that can be reused
by non-Qt entry points (e.g., CLI tools or automated tests).  The controller
operates on plain dictionaries via a lightweight :class:`CollageStateAdapter`
so that alternative front ends can provide their own state readers/writers
without depending on ``QWidget`` internals.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


class UndoUnavailableError(RuntimeError):
    """Raised when an undo operation is requested with no history."""


class RedoUnavailableError(RuntimeError):
    """Raised when a redo operation is requested with no history."""


@dataclass(frozen=True)
class CollageStateAdapter:
    """Adapter encapsulating how to read and apply collage state."""

    read_state: Callable[[], Dict[str, Any]]
    apply_state: Callable[[Dict[str, Any]], None]


class CollageSessionController:
    """Manage collage session history independently of UI widgets."""

    def __init__(
        self,
        adapter: CollageStateAdapter,
        *,
        history_limit: int = 30,
    ) -> None:
        if history_limit <= 0:
            raise ValueError("history_limit must be greater than zero")
        self._adapter = adapter
        self._history_limit = history_limit
        self._undo_stack: List[Dict[str, Any]] = []
        self._redo_stack: List[Dict[str, Any]] = []
        self._is_restoring = False
        self._history_baseline: Dict[str, Any] = copy.deepcopy(self._adapter.read_state())

    @property
    def is_restoring(self) -> bool:
        """Return whether the controller is currently applying a snapshot."""

        return self._is_restoring

    def capture_snapshot(self) -> bool:
        """Persist the current baseline state to the undo stack."""

        if self._is_restoring:
            return False
        snapshot = copy.deepcopy(self._history_baseline)
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        return True

    def discard_latest_snapshot(self) -> None:
        """Drop the most recently captured undo snapshot if present."""

        if self._undo_stack:
            self._undo_stack.pop()

    def update_baseline(self, state: Optional[Dict[str, Any]] = None) -> None:
        """Refresh the baseline to the provided or current state."""

        if state is None:
            state = self._adapter.read_state()
        self._history_baseline = copy.deepcopy(state)

    def reset_history(self) -> None:
        """Clear undo/redo stacks and resync the baseline from the adapter."""

        self._undo_stack.clear()
        self._redo_stack.clear()
        self.update_baseline()

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply a serialized state through the adapter and refresh baseline."""

        if not state:
            return
        self._is_restoring = True
        try:
            self._adapter.apply_state(copy.deepcopy(state))
        finally:
            self._is_restoring = False
        self.update_baseline(state)

    def undo(self) -> None:
        """Restore the previous snapshot, pushing the current state to redo."""

        if not self._undo_stack:
            raise UndoUnavailableError("No undo history is available")
        snapshot = self._undo_stack.pop()
        current = copy.deepcopy(self._adapter.read_state())
        self._redo_stack.append(current)
        if len(self._redo_stack) > self._history_limit:
            self._redo_stack.pop(0)
        self.restore_state(snapshot)

    def redo(self) -> None:
        """Reapply the next snapshot in the redo stack."""

        if not self._redo_stack:
            raise RedoUnavailableError("No redo history is available")
        snapshot = self._redo_stack.pop()
        current = copy.deepcopy(self._adapter.read_state())
        self._undo_stack.append(current)
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self.restore_state(snapshot)

    def current_state(self) -> Dict[str, Any]:
        """Return a deep copy of the current adapter state."""

        return copy.deepcopy(self._adapter.read_state())

