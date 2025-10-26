"""Unit tests for autosave serialization helpers."""
import pytest

pytest.importorskip(
    "PySide6.QtGui",
    reason="PySide6 GUI bindings unavailable in headless test env",
    exc_type=ImportError,
)

try:
    from src.serialization import autosave
except ImportError as exc:  # pragma: no cover - skip when Qt deps missing
    pytest.skip(f"Autosave serializer unavailable: {exc}")


def test_cell_state_payload_round_trip():
    payload = {
        "row": 1,
        "column": 2,
        "row_span": 3,
        "col_span": 4,
        "has_image": True,
        "image": "ZmFrZV9pbWFnZQ==",
        "caption": "Hello",
        "top_caption": "Top",
        "bottom_caption": "Bottom",
        "show_top_caption": False,
        "show_bottom_caption": True,
        "caption_font_family": "Arial",
        "caption_min_size": 10,
        "caption_max_size": 40,
        "caption_uppercase": True,
        "caption_stroke_width": 2,
        "caption_stroke_color": [255, 0, 0, 255],
        "caption_fill_color": [0, 0, 0, 255],
        "caption_safe_margin_ratio": 0.2,
        "caption_font_size": 12,
        "caption_bold": True,
        "caption_italic": False,
        "caption_underline": True,
        "transformation_mode": 0,
        "aspect_ratio_mode": 1,
        "selected": True,
    }
    state = autosave.CellAutosaveState.from_payload(payload)
    assert state.to_payload() == payload


def test_collage_state_round_trip():
    cell = autosave.CellAutosaveState.from_payload(
        {
            "row": 0,
            "column": 0,
            "row_span": 1,
            "col_span": 1,
            "has_image": False,
            "image": None,
            "caption": "",
            "top_caption": "",
            "bottom_caption": "",
            "show_top_caption": True,
            "show_bottom_caption": True,
            "caption_font_family": "",
            "caption_min_size": 0,
            "caption_max_size": 0,
            "caption_uppercase": False,
            "caption_stroke_width": 0,
            "caption_safe_margin_ratio": 0.0,
            "caption_font_size": 0,
            "caption_bold": False,
            "caption_italic": False,
            "caption_underline": False,
            "transformation_mode": None,
            "aspect_ratio_mode": None,
            "selected": False,
        }
    )
    merge = autosave.MergedCellState(row=0, column=0, row_span=2, col_span=2)
    snapshot = autosave.CollageAutosaveState(
        rows=2,
        columns=2,
        spacing=4,
        merged_cells=[merge],
        cells=[cell],
    )
    payload = autosave.serialize_snapshot(snapshot)
    restored = autosave.deserialize_snapshot(payload)
    assert restored == snapshot
