# widgets/collage.py
"""
Defines CollageWidget: a grid of CollageCell widgets with merge/split functionality.
"""
from typing import Optional, Tuple, List, Dict, Any
import logging

from PySide6.QtWidgets import QWidget, QGridLayout
from PySide6.QtCore import QSize

from .. import config
from .cell import CollageCell
from ..serialization import (
    CollageAutosaveState,
    CellAutosaveState,
    MergedCellState,
    serialize_snapshot,
    deserialize_snapshot,
)


class CollageWidget(QWidget):
    """
    Widget that manages a grid of CollageCell instances, supports merging and splitting.
    """

    _CELL_STATE_ATTRS = (
        "caption",
        "top_caption",
        "bottom_caption",
        "show_top_caption",
        "show_bottom_caption",
        "caption_font_family",
        "caption_min_size",
        "caption_max_size",
        "caption_uppercase",
        "caption_stroke_width",
        "caption_stroke_color",
        "caption_fill_color",
        "caption_safe_margin_ratio",
        "use_caption_formatting",
        "caption_font_size",
        "caption_bold",
        "caption_italic",
        "caption_underline",
        "transformation_mode",
        "aspect_ratio_mode",
    )

    def __init__(
        self,
        rows: int = config.DEFAULT_ROWS,
        columns: int = config.DEFAULT_COLUMNS,
        cell_size: int = config.DEFAULT_CELL_SIZE,
        parent=None
    ):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.cell_size = cell_size
        self.spacing = config.DEFAULT_SPACING
        self.merged_cells: Dict[Tuple[int,int], Tuple[int,int]] = {}
        self._cell_pos_map: Dict[CollageCell, Tuple[int,int]] = {}
        self._base_cell_size: Tuple[int, int] = (cell_size, cell_size)

        self._setup_layout()
        self.cells: List[CollageCell] = []
        self.populate_grid()
        # Allow widget to expand and recompute cell sizes on resize
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Accept external drops to auto-fill empty cells
        self.setAcceptDrops(True)

    def _setup_layout(self) -> None:
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(self.spacing)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)

    def _rectangle_in_bounds(self, start_row: int, start_col: int, rowspan: int, colspan: int) -> bool:
        if start_row < 0 or start_col < 0:
            return False
        if rowspan <= 0 or colspan <= 0:
            return False
        if start_row + rowspan > self.rows or start_col + colspan > self.columns:
            return False
        return True

    def _set_cell_size(self, cell: CollageCell, base_w: int, base_h: int) -> None:
        span_r = max(1, getattr(cell, "row_span", 1))
        span_c = max(1, getattr(cell, "col_span", 1))
        width = max(1, base_w * span_c + self.spacing * (span_c - 1))
        height = max(1, base_h * span_r + self.spacing * (span_r - 1))
        cell.setFixedSize(int(width), int(height))

    def _apply_sizes(self, base_w: Optional[int] = None, base_h: Optional[int] = None) -> None:
        if not self.cells:
            return
        if base_w is None or base_h is None:
            base_w, base_h = self._base_cell_size
        if base_w <= 0 or base_h <= 0:
            base_w = base_h = self.cell_size
        for cell in self.cells:
            self._set_cell_size(cell, base_w, base_h)

    def _snapshot_cells(self) -> Dict[Tuple[int, int], CellAutosaveState]:
        """Return a mapping of cell position to autosave-ready state."""
        state: Dict[Tuple[int, int], CellAutosaveState] = {}
        for cell, (row, col) in self._cell_pos_map.items():
            state[(row, col)] = CellAutosaveState.from_cell(cell, row=row, column=col)
        return state

    def _restore_cell(self, cell: CollageCell, state: CellAutosaveState) -> None:
        """Restore a cell's state from a serialized autosave snapshot."""
        state.apply_to_cell(cell)

    def serialize_for_autosave(self) -> Dict[str, Any]:
        """Return a JSON-serialisable snapshot of the collage grid."""
        snapshot = CollageAutosaveState(
            rows=self.rows,
            columns=self.columns,
            spacing=self.spacing,
            merged_cells=[
                MergedCellState(row=row, column=col, row_span=span[0], col_span=span[1])
                for (row, col), span in self.merged_cells.items()
            ],
            cells=[
                CellAutosaveState.from_cell(cell, row=row, column=col)
                for cell, (row, col) in self._cell_pos_map.items()
            ],
        )
        return serialize_snapshot(snapshot)

    def restore_from_serialized(self, state: Dict[str, Any]) -> None:
        """Restore previously serialized state produced by serialize_for_autosave."""
        if not state:
            return

        snapshot = deserialize_snapshot(state)

        # Attempt in-place restore when grid dimensions and merges match to preserve cell instances.
        existing_merges = {
            (row, col, span[0], span[1]) for (row, col), span in self.merged_cells.items()
        }
        snapshot_merges = {
            (merge.row, merge.column, merge.row_span, merge.col_span)
            for merge in snapshot.merged_cells
        }
        can_reuse_cells = (
            snapshot.rows == self.rows
            and snapshot.columns == self.columns
            and existing_merges == snapshot_merges
        )
        if can_reuse_cells:
            for cell_state in snapshot.cells:
                if not self.get_cell_at(cell_state.row, cell_state.column):
                    can_reuse_cells = False
                    break
        if can_reuse_cells:
            self.spacing = snapshot.spacing
            self.grid_layout.setSpacing(self.spacing)
            for cell_state in snapshot.cells:
                cell = self.get_cell_at(cell_state.row, cell_state.column)
                if cell:
                    cell_state.apply_to_cell(cell)
            self._apply_sizes()
            self.update()
            return

        if "spacing" in state:
            self.spacing = snapshot.spacing
        self.grid_layout.setSpacing(self.spacing)

        if "rows" in state:
            self.rows = snapshot.rows
        if "columns" in state:
            self.columns = snapshot.columns
        self.populate_grid()

        for merge in snapshot.merged_cells:
            self.merge_cells(
                merge.row,
                merge.column,
                merge.row_span,
                merge.col_span,
                require_selection=False,
            )

        for cell_state in snapshot.cells:
            cell = self.get_cell_at(cell_state.row, cell_state.column)
            if not cell:
                continue
            cell_state.apply_to_cell(cell)

        self._apply_sizes()
        self.update()

    def sizeHint(self) -> QSize:
        width = self.columns * self.cell_size + (self.columns - 1) * self.spacing
        height = self.rows * self.cell_size + (self.rows - 1) * self.spacing
        return QSize(width, height)

    def populate_grid(self) -> None:
        # Clear existing
        for cell in self.cells:
            self.grid_layout.removeWidget(cell)
            cell.deleteLater()
        self.cells.clear()
        self._cell_pos_map.clear()

        # Create cells
        for r in range(self.rows):
            for c in range(self.columns):
                cell_id = r * self.columns + c + 1
                cell = CollageCell(cell_id, self.cell_size, self)
                self.grid_layout.addWidget(cell, r, c)
                self.cells.append(cell)
                self._cell_pos_map[cell] = (r, c)
        self._apply_sizes()
        logging.info("CollageWidget: populated %dx%d grid.", self.rows, self.columns)

    def get_cell_position(self, cell: CollageCell) -> Optional[Tuple[int,int]]:
        """Return the (row, col) of a cell or None if not found."""
        return self._cell_pos_map.get(cell)

    def get_cell_at(self, row: int, col: int) -> Optional[CollageCell]:
        """Return the cell instance at grid position."""
        # Check merged cells
        if (row, col) in self.merged_cells:
            # top-left of merged
            for cell, pos in self._cell_pos_map.items():
                if pos == (row, col):
                    return cell
            return None
        # Regular
        for cell, pos in self._cell_pos_map.items():
            if pos == (row, col):
                return cell
        return None

    def is_valid_merge(self, start_row: int, start_col: int, rowspan: int, colspan: int) -> bool:
        """Ensure a rectangle is fully selected and within bounds."""
        # Bounds
        if start_row < 0 or start_col < 0 or start_row + rowspan > self.rows or start_col + colspan > self.columns:
            logging.warning("Merge out of bounds: (%d,%d) span %dx%d", start_row, start_col, rowspan, colspan)
            return False

        # Required positions
        required = {(r, c) for r in range(start_row, start_row + rowspan)
                             for c in range(start_col, start_col + colspan)}
        # Selected positions
        selected = set()
        for cell in self.cells:
            if cell.selected:
                pos = self.get_cell_position(cell)
                if not pos:
                    continue
                # Expand if part of existing merge
                for (mr, mc), (mrs, mcs) in self.merged_cells.items():
                    if mr <= pos[0] < mr + mrs and mc <= pos[1] < mc + mcs:
                        for rr in range(mr, mr + mrs):
                            for cc in range(mc, mc + mcs):
                                selected.add((rr, cc))
                        break
                else:
                    selected.add(pos)
        if not required.issubset(selected):
            logging.warning("Not all required cells are selected for merge.")
            return False
        return True

    def merge_cells(self, start_row: int, start_col: int, rowspan: int, colspan: int, *, require_selection: bool = True) -> bool:
        """Merge a block into one cell.

        Args:
            require_selection: When ``True`` (default) the selection must already
            cover the rectangle; set to ``False`` for programmatic restores.
        """
        if require_selection:
            if not self.is_valid_merge(start_row, start_col, rowspan, colspan):
                return False
        else:
            if not self._rectangle_in_bounds(start_row, start_col, rowspan, colspan):
                logging.warning(
                    "Merge out of bounds (programmatic): (%d,%d) span %dx%d",
                    start_row,
                    start_col,
                    rowspan,
                    colspan,
                )
                return False

        # Identify target and others
        target = self.get_cell_at(start_row, start_col)
        if not target:
            logging.warning("Merge failed: no cell at (%d,%d)", start_row, start_col)
            return False
        others = []
        for r in range(start_row, start_row + rowspan):
            for c in range(start_col, start_col + colspan):
                if r == start_row and c == start_col:
                    continue
                cell = self.get_cell_at(r, c)
                if cell:
                    others.append(cell)

        # Remove others
        for cell in others:
            self.grid_layout.removeWidget(cell)
            del self._cell_pos_map[cell]
            self.cells.remove(cell)
            cell.deleteLater()

        # Adjust target
        self.grid_layout.addWidget(target, start_row, start_col, rowspan, colspan)
        self.merged_cells[(start_row, start_col)] = (rowspan, colspan)
        self._cell_pos_map[target] = (start_row, start_col)
        target.row_span = rowspan
        target.col_span = colspan
        self._apply_sizes()

        logging.info("Merged at (%d,%d) span %dx%d", start_row, start_col, rowspan, colspan)
        return True

    def split_cells(self, row: int, col: int) -> bool:
        """Split a previously merged cell back into grid cells."""
        key = (row, col)
        if key not in self.merged_cells:
            logging.warning("No merged cell at (%d,%d) to split.", row, col)
            return False
        rowspan, colspan = self.merged_cells.pop(key)
        merged_cell = self.get_cell_at(row, col)
        if not merged_cell:
            return False

        # Preserve state
        pix = merged_cell.original_pixmap
        caption = merged_cell.caption
        selected = merged_cell.selected

        # Remove merged from layout
        self.grid_layout.removeWidget(merged_cell)
        del self._cell_pos_map[merged_cell]
        if merged_cell in self.cells:
            self.cells.remove(merged_cell)
        merged_cell.deleteLater()

        # Create new individual cells
        for r in range(row, row + rowspan):
            for c in range(col, col + colspan):
                cell_id = len(self.cells) + 1
                cell = CollageCell(cell_id, self.cell_size, self)
                if r == row and c == col:
                    if pix:
                        cell.setImage(pix, original=pix)
                    cell.caption = caption
                    cell.selected = selected
                    cell.update()
                self.grid_layout.addWidget(cell, r, c)
                self.cells.append(cell)
                self._cell_pos_map[cell] = (r, c)
        self._apply_sizes()
        logging.info("Split merged cell at (%d,%d)", row, col)
        return True

    def update_grid(self, rows: int, columns: int) -> None:
        """Resize grid, reapply valid merges, and restore cell content."""
        preserved = self._snapshot_cells()
        self.rows, self.columns = rows, columns
        old_merges = self.merged_cells.copy()
        self.merged_cells.clear()
        self.populate_grid()
        for (r, c), (rs, cs) in old_merges.items():
            if r + rs <= rows and c + cs <= columns:
                self.merge_cells(r, c, rs, cs, require_selection=False)
        for (r, c), data in preserved.items():
            if r >= self.rows or c >= self.columns:
                continue
            cell = self.get_cell_at(r, c)
            if not cell:
                continue
            self._restore_cell(cell, data)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Compute square cell size to fit current widget size with spacing
        if self.columns <= 0 or self.rows <= 0:
            return
        total_w = max(0, self.width() - (self.columns - 1) * self.spacing)
        total_h = max(0, self.height() - (self.rows - 1) * self.spacing)
        cell_w = max(1, total_w // self.columns)
        cell_h = max(1, total_h // self.rows)
        self._base_cell_size = (cell_w, cell_h)
        self._apply_sizes(cell_w, cell_h)

    def merge_selected(self) -> bool:
        """Convenience: merge all selected cells if they form a rectangle."""
        rect = self.selected_rectangle()
        if not rect:
            return False
        r, c, rs, cs = rect
        return self.merge_cells(r, c, rs, cs)

    def selected_rectangle(self) -> Optional[Tuple[int, int, int, int]]:
        """Return (row, col, rowspan, colspan) if selection is a filled rectangle.

        Returns None if fewer than 2 cells are selected or the selection is non-rectangular.
        """
        positions = [self.get_cell_position(c) for c in self.cells if c.selected]
        positions = [p for p in positions if p]
        if len(positions) < 2:
            return None
        rows = [r for r, _ in positions]
        cols = [c for _, c in positions]
        r0, r1 = min(rows), max(rows)
        c0, c1 = min(cols), max(cols)
        required = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)}
        if set(positions) != required:
            return None
        return r0, c0, (r1 - r0 + 1), (c1 - c0 + 1)

    # --- Drag & drop to fill grid ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        self._fill_empty_cells(paths)
        event.acceptProposedAction()

    def _fill_empty_cells(self, paths: List[str]) -> None:
        empties = [c for c in self.cells if not getattr(c, 'pixmap', None)]
        if not empties:
            return
        for pth, cell in zip(paths, empties):
            try:
                cell._load_image(pth)  # reuse existing loader with validation and optimization
            except Exception:
                continue

    def clear(self) -> None:
        """Reset entire grid to initial empty state."""
        self.merged_cells.clear()
        self.populate_grid()
        logging.info("CollageWidget: grid cleared.")
