"""Autosave serialization helpers decoupled from widget internals."""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QPixmap


LOGGER = logging.getLogger(__name__)


ColorTuple = Tuple[int, int, int, int]


def color_to_rgba(color: Optional[QColor]) -> Optional[ColorTuple]:
    """Convert a QColor into an (r, g, b, a) tuple."""
    if color is None:
        return None
    r, g, b, a = color.getRgb()
    return int(r), int(g), int(b), int(a)


def rgba_to_qcolor(value: Optional[Sequence[int]]) -> Optional[QColor]:
    """Create a QColor from a sequence of channel values."""
    if value is None:
        return None
    channels = list(value)
    if len(channels) == 3:
        channels.append(255)
    if len(channels) != 4:
        LOGGER.warning("Invalid color channel data for QColor: %s", value)
        return None
    try:
        return QColor(*[int(c) for c in channels])
    except (TypeError, ValueError):
        LOGGER.warning("Failed to coerce color channels into QColor: %s", value)
        return None


def enum_to_int(value: Any) -> Optional[int]:
    """Return an integer representation of a Qt enum if possible."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    candidate = getattr(value, "value", value)
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return None


def encode_pixmap(pixmap: Optional[QPixmap]) -> Optional[str]:
    """Encode a pixmap into a base64 PNG string."""
    if not pixmap or pixmap.isNull():
        return None
    buffer = QBuffer()
    if not buffer.open(QIODevice.WriteOnly):
        LOGGER.warning("Unable to open QBuffer for pixmap encoding")
        return None
    if not pixmap.save(buffer, "PNG"):
        LOGGER.warning("Unable to save pixmap to buffer during encoding")
        return None
    return base64.b64encode(bytes(buffer.data())).decode("ascii")


def decode_pixmap(encoded: Optional[str]) -> Optional[QPixmap]:
    """Decode a base64 PNG string into a QPixmap."""
    if not encoded:
        return None
    try:
        raw = QByteArray.fromBase64(encoded.encode("ascii"))
    except Exception as exc:  # noqa: BLE001 - PySide wraps exceptions inconsistently
        LOGGER.warning("Failed to decode pixmap: invalid base64 input", exc_info=exc)
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(bytes(raw), "PNG"):
        LOGGER.warning("Failed to load pixmap from decoded data")
        return None
    return pixmap


@dataclass(eq=True, frozen=True)
class MergedCellState:
    """Representation of a merged cell block."""

    row: int
    column: int
    row_span: int
    col_span: int

    def to_payload(self) -> Dict[str, int]:
        return {
            "row": self.row,
            "column": self.column,
            "row_span": self.row_span,
            "col_span": self.col_span,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MergedCellState":
        return cls(
            row=int(payload.get("row", 0)),
            column=int(payload.get("column", 0)),
            row_span=int(payload.get("row_span", 1)),
            col_span=int(payload.get("col_span", 1)),
        )


@dataclass(eq=True, frozen=True)
class CellAutosaveState:
    """Serializable snapshot of a collage cell."""

    row: int
    column: int
    row_span: int
    col_span: int
    has_image: bool
    image: Optional[str]
    caption: str
    top_caption: str
    bottom_caption: str
    show_top_caption: bool
    show_bottom_caption: bool
    caption_font_family: str
    caption_min_size: int
    caption_max_size: int
    caption_uppercase: bool
    caption_stroke_width: int
    caption_stroke_color: Optional[ColorTuple]
    caption_fill_color: Optional[ColorTuple]
    caption_safe_margin_ratio: float
    caption_font_size: int
    caption_bold: bool
    caption_italic: bool
    caption_underline: bool
    transformation_mode: Optional[int]
    aspect_ratio_mode: Optional[int]
    selected: bool

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "row": self.row,
            "column": self.column,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "has_image": self.has_image,
            "image": self.image,
            "caption": self.caption,
            "top_caption": self.top_caption,
            "bottom_caption": self.bottom_caption,
            "show_top_caption": self.show_top_caption,
            "show_bottom_caption": self.show_bottom_caption,
            "caption_font_family": self.caption_font_family,
            "caption_min_size": self.caption_min_size,
            "caption_max_size": self.caption_max_size,
            "caption_uppercase": self.caption_uppercase,
            "caption_stroke_width": self.caption_stroke_width,
            "caption_safe_margin_ratio": self.caption_safe_margin_ratio,
            "caption_font_size": self.caption_font_size,
            "caption_bold": self.caption_bold,
            "caption_italic": self.caption_italic,
            "caption_underline": self.caption_underline,
            "transformation_mode": self.transformation_mode,
            "aspect_ratio_mode": self.aspect_ratio_mode,
            "selected": self.selected,
        }
        if self.caption_stroke_color is not None:
            payload["caption_stroke_color"] = list(self.caption_stroke_color)
        if self.caption_fill_color is not None:
            payload["caption_fill_color"] = list(self.caption_fill_color)
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "CellAutosaveState":
        stroke_color = payload.get("caption_stroke_color")
        fill_color = payload.get("caption_fill_color")
        return cls(
            row=int(payload.get("row", 0)),
            column=int(payload.get("column", 0)),
            row_span=int(payload.get("row_span", 1)),
            col_span=int(payload.get("col_span", 1)),
            has_image=bool(payload.get("has_image", False)),
            image=payload.get("image"),
            caption=str(payload.get("caption", "")),
            top_caption=str(payload.get("top_caption", "")),
            bottom_caption=str(payload.get("bottom_caption", "")),
            show_top_caption=bool(payload.get("show_top_caption", True)),
            show_bottom_caption=bool(payload.get("show_bottom_caption", True)),
            caption_font_family=str(payload.get("caption_font_family", "")),
            caption_min_size=int(payload.get("caption_min_size", 0)),
            caption_max_size=int(payload.get("caption_max_size", 0)),
            caption_uppercase=bool(payload.get("caption_uppercase", False)),
            caption_stroke_width=int(payload.get("caption_stroke_width", 0)),
            caption_stroke_color=None
            if stroke_color is None
            else tuple(int(c) for c in stroke_color),
            caption_fill_color=None
            if fill_color is None
            else tuple(int(c) for c in fill_color),
            caption_safe_margin_ratio=float(payload.get("caption_safe_margin_ratio", 0.0)),
            caption_font_size=int(payload.get("caption_font_size", 0)),
            caption_bold=bool(payload.get("caption_bold", False)),
            caption_italic=bool(payload.get("caption_italic", False)),
            caption_underline=bool(payload.get("caption_underline", False)),
            transformation_mode=payload.get("transformation_mode"),
            aspect_ratio_mode=payload.get("aspect_ratio_mode"),
            selected=bool(payload.get("selected", False)),
        )

    @classmethod
    def from_cell(cls, cell: Any, *, row: int, column: int) -> "CellAutosaveState":
        """Build a snapshot from a CollageCell-like object."""
        image_source = getattr(cell, "original_pixmap", None) or getattr(cell, "pixmap", None)
        cached_payload = getattr(cell, "autosave_payload", None)
        image_payload = cached_payload if cached_payload is not None else encode_pixmap(image_source)
        return cls(
            row=row,
            column=column,
            row_span=int(getattr(cell, "row_span", 1)),
            col_span=int(getattr(cell, "col_span", 1)),
            has_image=bool(getattr(cell, "pixmap", None)),
            image=image_payload,
            caption=str(getattr(cell, "caption", "")),
            top_caption=str(getattr(cell, "top_caption", "")),
            bottom_caption=str(getattr(cell, "bottom_caption", "")),
            show_top_caption=bool(getattr(cell, "show_top_caption", True)),
            show_bottom_caption=bool(getattr(cell, "show_bottom_caption", True)),
            caption_font_family=str(getattr(cell, "caption_font_family", "")),
            caption_min_size=int(getattr(cell, "caption_min_size", 0)),
            caption_max_size=int(getattr(cell, "caption_max_size", 0)),
            caption_uppercase=bool(getattr(cell, "caption_uppercase", False)),
            caption_stroke_width=int(getattr(cell, "caption_stroke_width", 0)),
            caption_stroke_color=color_to_rgba(getattr(cell, "caption_stroke_color", None)),
            caption_fill_color=color_to_rgba(getattr(cell, "caption_fill_color", None)),
            caption_safe_margin_ratio=float(getattr(cell, "caption_safe_margin_ratio", 0.0)),
            caption_font_size=int(getattr(cell, "caption_font_size", 0)),
            caption_bold=bool(getattr(cell, "caption_bold", False)),
            caption_italic=bool(getattr(cell, "caption_italic", False)),
            caption_underline=bool(getattr(cell, "caption_underline", False)),
            transformation_mode=enum_to_int(getattr(cell, "transformation_mode", None)),
            aspect_ratio_mode=enum_to_int(getattr(cell, "aspect_ratio_mode", None)),
            selected=bool(getattr(cell, "selected", False)),
        )

    def apply_to_cell(self, cell: Any) -> None:
        """Apply the snapshot state back onto a CollageCell-like object."""
        encoded_image = self.image
        pixmap = decode_pixmap(encoded_image)
        if pixmap:
            cell.setImage(pixmap, original=pixmap)
        else:
            cell.clearImage()
        if hasattr(cell, "set_autosave_payload"):
            cell.set_autosave_payload(encoded_image if pixmap else None)
        for attr, value in (
            ("caption", self.caption),
            ("top_caption", self.top_caption),
            ("bottom_caption", self.bottom_caption),
            ("show_top_caption", self.show_top_caption),
            ("show_bottom_caption", self.show_bottom_caption),
            ("caption_font_family", self.caption_font_family),
            ("caption_min_size", self.caption_min_size),
            ("caption_max_size", self.caption_max_size),
            ("caption_uppercase", self.caption_uppercase),
            ("caption_stroke_width", self.caption_stroke_width),
            ("caption_safe_margin_ratio", self.caption_safe_margin_ratio),
            ("caption_font_size", self.caption_font_size),
            ("caption_bold", self.caption_bold),
            ("caption_italic", self.caption_italic),
            ("caption_underline", self.caption_underline),
            ("selected", self.selected),
        ):
            setattr(cell, attr, value)
        if self.caption_stroke_color is not None:
            stroke = rgba_to_qcolor(self.caption_stroke_color)
            setattr(cell, "caption_stroke_color", stroke)
        else:
            setattr(cell, "caption_stroke_color", None)
        if self.caption_fill_color is not None:
            fill = rgba_to_qcolor(self.caption_fill_color)
            setattr(cell, "caption_fill_color", fill)
        else:
            setattr(cell, "caption_fill_color", None)
        if self.transformation_mode is not None:
            try:
                setattr(cell, "transformation_mode", Qt.TransformationMode(int(self.transformation_mode)))
            except (TypeError, ValueError):
                setattr(cell, "transformation_mode", None)
        else:
            setattr(cell, "transformation_mode", None)
        if self.aspect_ratio_mode is not None:
            try:
                setattr(cell, "aspect_ratio_mode", Qt.AspectRatioMode(int(self.aspect_ratio_mode)))
            except (TypeError, ValueError):
                setattr(cell, "aspect_ratio_mode", None)
        else:
            setattr(cell, "aspect_ratio_mode", None)
        cell.row_span = int(self.row_span)
        cell.col_span = int(self.col_span)
        cell.update()


@dataclass(eq=True, frozen=True)
class CollageAutosaveState:
    """Serializable snapshot of a collage grid."""

    rows: int
    columns: int
    spacing: int
    merged_cells: List[MergedCellState] = field(default_factory=list)
    cells: List[CellAutosaveState] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "rows": self.rows,
            "columns": self.columns,
            "spacing": self.spacing,
            "merged_cells": [merge.to_payload() for merge in self.merged_cells],
            "cells": [cell.to_payload() for cell in self.cells],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "CollageAutosaveState":
        merges = [
            MergedCellState.from_payload(entry)
            for entry in payload.get("merged_cells", [])
        ]
        cells = [
            CellAutosaveState.from_payload(entry)
            for entry in payload.get("cells", [])
        ]
        return cls(
            rows=int(payload.get("rows", 0)),
            columns=int(payload.get("columns", 0)),
            spacing=int(payload.get("spacing", 0)),
            merged_cells=merges,
            cells=cells,
        )

    @classmethod
    def from_widget(cls, widget: Any) -> "CollageAutosaveState":
        """Capture the current widget state into a serializable snapshot."""
        merged = [
            MergedCellState(row=row, column=col, row_span=span[0], col_span=span[1])
            for (row, col), span in getattr(widget, "merged_cells", {}).items()
        ]
        cells: List[CellAutosaveState] = []
        cell_map: Iterable[Tuple[Any, Tuple[int, int]]] = getattr(widget, "_cell_pos_map", {}).items()
        for cell, (row, col) in cell_map:
            cells.append(CellAutosaveState.from_cell(cell, row=row, column=col))
        return cls(
            rows=int(getattr(widget, "rows", 0)),
            columns=int(getattr(widget, "columns", 0)),
            spacing=int(getattr(widget, "spacing", 0)),
            merged_cells=merged,
            cells=cells,
        )


def serialize_snapshot(state: CollageAutosaveState) -> Dict[str, Any]:
    """Convert a snapshot into JSON-serialisable primitives."""
    return state.to_payload()


def deserialize_snapshot(payload: Mapping[str, Any]) -> CollageAutosaveState:
    """Reconstruct a snapshot from JSON-serialisable primitives."""
    return CollageAutosaveState.from_payload(payload)
