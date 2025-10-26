"""Tests for autosave serialization helpers."""
from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip(
    "PySide6.QtGui",
    reason="PySide6 with GUI dependencies is required for serialization tests",
    exc_type=ImportError,
)

from src.serialization import CellAutosaveState


class _StubCell:
    """Simple stand-in for a CollageCell when testing serialization."""

    def __init__(self, autosave_payload: str | None) -> None:
        self.row_span = 1
        self.col_span = 1
        self.pixmap = object()
        self.original_pixmap = object()
        self.caption = ""
        self.top_caption = ""
        self.bottom_caption = ""
        self.show_top_caption = True
        self.show_bottom_caption = True
        self.caption_font_family = "Impact"
        self.caption_min_size = 12
        self.caption_max_size = 48
        self.caption_uppercase = True
        self.caption_stroke_width = 3
        self.caption_stroke_color = None
        self.caption_fill_color = None
        self.caption_safe_margin_ratio = 0.0
        self.caption_font_size = 14
        self.caption_bold = True
        self.caption_italic = False
        self.caption_underline = False
        self.transformation_mode = None
        self.aspect_ratio_mode = None
        self.selected = False
        self.autosave_payload = autosave_payload


def test_cell_autosave_state_prefers_cached_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Using an existing autosave payload must avoid re-encoding on demand."""

    def _fail_encode(_: Any) -> str:
        raise AssertionError("encode_pixmap should not run when cache is present")

    monkeypatch.setattr("src.serialization.autosave.encode_pixmap", _fail_encode)
    cell = _StubCell(autosave_payload="cached")

    state = CellAutosaveState.from_cell(cell, row=0, column=0)

    assert state.image == "cached"


def test_cell_autosave_state_encodes_when_missing_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no cache exists the encoder should provide the payload."""

    monkeypatch.setattr("src.serialization.autosave.encode_pixmap", lambda _: "encoded")
    cell = _StubCell(autosave_payload=None)

    state = CellAutosaveState.from_cell(cell, row=1, column=2)

    assert state.image == "encoded"
