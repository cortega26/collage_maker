"""Grid layout management for collage editing.

This module provides a pure-Python representation of a grid based collage
layout.  It supports merging and splitting cells, per-cell aspect settings
and undo/redo of layout operations.  The class is UI agnostic so it can be
unit tested without a Qt environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
import json
import copy


@dataclass
class LayoutCell:
    """Represents a single cell in the collage grid."""

    id: int
    row: int
    column: int
    row_span: int = 1
    col_span: int = 1
    aspect_mode: str = "free"  # "free" or "fixed"
    ratio: Optional[Tuple[int, int]] = None  # Used when aspect_mode=="fixed"
    fit_mode: str = "fit"  # "fit" or "fill"
    align: str = "center"  # alignment keyword

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "row": self.row,
            "column": self.column,
            "rowSpan": self.row_span,
            "colSpan": self.col_span,
            "aspectMode": self.aspect_mode,
            "fitMode": self.fit_mode,
            "align": self.align,
        }
        if self.aspect_mode == "fixed" and self.ratio:
            data["ratio"] = f"{self.ratio[0]}:{self.ratio[1]}"
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayoutCell":
        ratio = None
        if "ratio" in data and data.get("aspectMode") == "fixed":
            parts = data["ratio"].split(":")
            if len(parts) == 2:
                ratio = (int(parts[0]), int(parts[1]))
        return cls(
            id=data["id"],
            row=data["row"],
            column=data["column"],
            row_span=data.get("rowSpan", 1),
            col_span=data.get("colSpan", 1),
            aspect_mode=data.get("aspectMode", "free"),
            ratio=ratio,
            fit_mode=data.get("fitMode", "fit"),
            align=data.get("align", "center"),
        )


class GridLayoutManager:
    """Maintain and edit a grid based collage layout."""

    def __init__(self, rows: int, columns: int, gutter: int = 0, padding: int = 0):
        if rows <= 0 or columns <= 0:
            raise ValueError("Grid must have positive dimensions")
        self.rows = rows
        self.columns = columns
        self.gutter = gutter
        self.padding = padding
        self.cells: List[LayoutCell] = [
            LayoutCell(id=r * columns + c, row=r, column=c)
            for r in range(rows)
            for c in range(columns)
        ]
        self._next_id = rows * columns
        self._undo_stack: List[List[LayoutCell]] = []
        self._redo_stack: List[List[LayoutCell]] = []
        self.last_emitted: str = self._emit_layout()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _snapshot(self) -> None:
        self._undo_stack.append(copy.deepcopy(self.cells))
        self._redo_stack.clear()

    def _emit_layout(self) -> str:
        layout = {
            "cells": [c.to_dict() for c in sorted(self.cells, key=lambda x: (x.row, x.column))],
            "gutter": self.gutter,
            "padding": self.padding,
        }
        self.last_emitted = json.dumps(layout, separators=(",", ":"))
        return self.last_emitted

    def _cell_at(self, row: int, column: int) -> Optional[LayoutCell]:
        for cell in self.cells:
            if cell.row == row and cell.column == column:
                return cell
            if cell.row <= row < cell.row + cell.row_span and \
               cell.column <= column < cell.column + cell.col_span:
                # inside merged cell but not top-left
                return None
        return None

    def _occupied_positions(self, exclude: Optional[int] = None) -> set[Tuple[int, int]]:
        occupied: set[Tuple[int, int]] = set()
        for cell in self.cells:
            if exclude is not None and cell.id == exclude:
                continue
            for r in range(cell.row, cell.row + cell.row_span):
                for c in range(cell.column, cell.column + cell.col_span):
                    occupied.add((r, c))
        return occupied

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def merge(self, positions: List[Tuple[int, int]]) -> str:
        """Merge cells at the given positions into a single cell.

        The positions must form a filled rectangle; otherwise a ValueError is
        raised.  Returns the updated layout JSON.
        """
        if len(positions) < 2:
            raise ValueError("Need at least two cells to merge")

        rows = [r for r, _ in positions]
        cols = [c for _, c in positions]
        min_r, max_r = min(rows), max(rows)
        min_c, max_c = min(cols), max(cols)

        required = {
            (r, c)
            for r in range(min_r, max_r + 1)
            for c in range(min_c, max_c + 1)
        }
        selected = set(positions)
        if selected != required:
            raise ValueError("Selection must form a contiguous rectangle")

        cell_map = {(c.row, c.column): c for c in self.cells}
        to_merge: List[LayoutCell] = []
        for pos in required:
            cell = cell_map.get(pos)
            if not cell or cell.row_span != 1 or cell.col_span != 1:
                raise ValueError("Cells must be unmerged before merging")
            to_merge.append(cell)

        self._snapshot()
        for cell in to_merge:
            self.cells.remove(cell)

        self._next_id += 1
        merged = LayoutCell(
            id=self._next_id,
            row=min_r,
            column=min_c,
            row_span=max_r - min_r + 1,
            col_span=max_c - min_c + 1,
        )
        self.cells.append(merged)
        return self._emit_layout()

    def split(self, cell_id: int, rows: int, cols: int) -> str:
        """Split a cell into an R x C grid.

        The cell's current span must be divisible by ``rows`` and ``cols``.
        Returns updated layout JSON.
        """
        if rows <= 0 or cols <= 0:
            raise ValueError("rows and cols must be positive")
        cell = next((c for c in self.cells if c.id == cell_id), None)
        if not cell:
            raise ValueError("Cell not found")
        if cell.row_span % rows != 0 or cell.col_span % cols != 0:
            raise ValueError("Cell span not divisible by requested split")

        sub_r = cell.row_span // rows
        sub_c = cell.col_span // cols

        self._snapshot()
        self.cells.remove(cell)
        for r in range(rows):
            for c in range(cols):
                self._next_id += 1
                self.cells.append(
                    LayoutCell(
                        id=self._next_id,
                        row=cell.row + r * sub_r,
                        column=cell.column + c * sub_c,
                        row_span=sub_r,
                        col_span=sub_c,
                    )
                )
        return self._emit_layout()

    def resize(self, cell_id: int, row_span: int, col_span: int) -> str:
        """Resize a cell to the given span ensuring no overlap."""
        if row_span <= 0 or col_span <= 0:
            raise ValueError("Spans must be positive")
        cell = next((c for c in self.cells if c.id == cell_id), None)
        if not cell:
            raise ValueError("Cell not found")
        if cell.row + row_span > self.rows or cell.column + col_span > self.columns:
            raise ValueError("Resize would exceed grid bounds")

        occupied = self._occupied_positions(exclude=cell_id)
        new_area = {
            (r, c)
            for r in range(cell.row, cell.row + row_span)
            for c in range(cell.column, cell.column + col_span)
        }
        if occupied & new_area:
            raise ValueError("Resize would overlap another cell")

        self._snapshot()
        cell.row_span = row_span
        cell.col_span = col_span
        return self._emit_layout()

    def set_aspect(
        self,
        cell_id: int,
        *,
        aspect_mode: str = "free",
        ratio: Optional[Tuple[int, int]] = None,
        fit_mode: str = "fit",
        align: str = "center",
    ) -> str:
        """Update aspect and alignment settings for a cell."""
        cell = next((c for c in self.cells if c.id == cell_id), None)
        if not cell:
            raise ValueError("Cell not found")
        if aspect_mode == "fixed" and not ratio:
            raise ValueError("Fixed aspect mode requires a ratio")
        self._snapshot()
        cell.aspect_mode = aspect_mode
        cell.ratio = ratio if aspect_mode == "fixed" else None
        cell.fit_mode = fit_mode
        cell.align = align
        return self._emit_layout()

    def undo(self) -> str:
        if not self._undo_stack:
            raise ValueError("Nothing to undo")
        self._redo_stack.append(copy.deepcopy(self.cells))
        self.cells = self._undo_stack.pop()
        return self._emit_layout()

    def redo(self) -> str:
        if not self._redo_stack:
            raise ValueError("Nothing to redo")
        self._undo_stack.append(copy.deepcopy(self.cells))
        self.cells = self._redo_stack.pop()
        return self._emit_layout()

    def to_json(self) -> str:
        return self._emit_layout()

    @classmethod
    def from_json(cls, layout_json: str) -> "GridLayoutManager":
        data = json.loads(layout_json)
        cells = [LayoutCell.from_dict(cd) for cd in data.get("cells", [])]
        rows = 0
        cols = 0
        for c in cells:
            rows = max(rows, c.row + c.row_span)
            cols = max(cols, c.column + c.col_span)
        mgr = cls(rows, cols, gutter=data.get("gutter", 0), padding=data.get("padding", 0))
        mgr.cells = cells
        mgr._next_id = max((c.id for c in cells), default=0)
        mgr._undo_stack.clear()
        mgr._redo_stack.clear()
        mgr.last_emitted = mgr._emit_layout()
        return mgr
