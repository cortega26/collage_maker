"""Serialization helpers for Collage Maker."""

from .autosave import (
    CollageAutosaveState,
    CellAutosaveState,
    MergedCellState,
    serialize_snapshot,
    deserialize_snapshot,
    encode_pixmap,
    decode_pixmap,
    color_to_rgba,
    rgba_to_qcolor,
    enum_to_int,
)

__all__ = [
    "CollageAutosaveState",
    "CellAutosaveState",
    "MergedCellState",
    "serialize_snapshot",
    "deserialize_snapshot",
    "encode_pixmap",
    "decode_pixmap",
    "color_to_rgba",
    "rgba_to_qcolor",
    "enum_to_int",
]
