"""Unit tests for the collage session controller service."""

from __future__ import annotations

from typing import Dict

import pytest

from src.controllers import (
    CollageSessionController,
    CollageStateAdapter,
    RedoUnavailableError,
    UndoUnavailableError,
)


def _make_state_adapter(initial: int = 1):
    holder: Dict[str, int] = {"value": initial}

    def read_state() -> Dict[str, int]:
        return {"value": holder["value"]}

    def apply_state(state: Dict[str, int]) -> None:
        holder["value"] = state["value"]

    adapter = CollageStateAdapter(read_state=read_state, apply_state=apply_state)
    return holder, adapter


def test_session_controller_undo_redo_roundtrip():
    holder, adapter = _make_state_adapter(initial=1)
    controller = CollageSessionController(adapter, history_limit=5)

    assert controller.capture_snapshot() is True

    holder["value"] = 2
    controller.update_baseline()
    controller.capture_snapshot()

    holder["value"] = 3
    controller.update_baseline()

    controller.undo()
    assert holder["value"] == 2

    controller.undo()
    assert holder["value"] == 1

    controller.redo()
    assert holder["value"] == 2

    controller.redo()
    assert holder["value"] == 3


def test_session_controller_discards_latest_snapshot():
    holder, adapter = _make_state_adapter(initial=10)
    controller = CollageSessionController(adapter, history_limit=2)

    controller.capture_snapshot()
    holder["value"] = 11
    controller.update_baseline()
    controller.capture_snapshot()
    controller.discard_latest_snapshot()

    holder["value"] = 20
    controller.update_baseline()

    controller.undo()
    assert holder["value"] == 10

    with pytest.raises(UndoUnavailableError):
        controller.undo()

    controller.redo()
    assert holder["value"] == 20

    with pytest.raises(RedoUnavailableError):
        controller.redo()
