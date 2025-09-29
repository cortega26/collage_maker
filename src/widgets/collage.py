# widgets/collage.py
"""
Defines CollageWidget: a grid of CollageCell widgets with merge/split functionality.
"""
from typing import Optional, Tuple, List, Dict
import logging

from PySide6.QtWidgets import QWidget, QGridLayout
from PySide6.QtCore import QSize

import config
from widgets.cell import CollageCell


class CollageWidget(QWidget):
    """
    Widget that manages a grid of CollageCell instances, supports merging and splitting.
    """
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

        self._setup_layout()
        self.cells: List[CollageCell] = []
        self.populate_grid()
        self.setFixedSize(self.sizeHint())

    def _setup_layout(self) -> None:
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(self.spacing)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)

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

    def merge_cells(self, start_row: int, start_col: int, rowspan: int, colspan: int) -> bool:
        """Merge a block into one cell."""
        if not self.is_valid_merge(start_row, start_col, rowspan, colspan):
            return False

        # Identify target and others
        target = self.get_cell_at(start_row, start_col)
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
        target.setFixedSize(
            self.cell_size * colspan + (colspan - 1) * self.spacing,
            self.cell_size * rowspan + (rowspan - 1) * self.spacing
        )
        self._cell_pos_map[target] = (start_row, start_col)
        target.row_span = rowspan
        target.col_span = colspan

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
                        cell.setImage(pix)
                    cell.caption = caption
                    cell.selected = selected
                    cell.update()
                self.grid_layout.addWidget(cell, r, c)
                self.cells.append(cell)
                self._cell_pos_map[cell] = (r, c)

        logging.info("Split merged cell at (%d,%d)", row, col)
        return True

    def update_grid(self, rows: int, columns: int) -> None:
        """Resize grid, reapply valid merges."""
        self.rows, self.columns = rows, columns
        old_merges = self.merged_cells.copy()
        self.merged_cells.clear()
        self.populate_grid()
        for (r, c), (rs, cs) in old_merges.items():
            if r + rs <= rows and c + cs <= columns:
                self.merge_cells(r, c, rs, cs)
        self.setFixedSize(self.sizeHint())

    def merge_selected(self) -> bool:
        """Convenience: merge all currently selected into a rectangle."""
        selected = [(cell, self.get_cell_position(cell)) for cell in self.cells if cell.selected]
        if len(selected) < 2:
            return False
        # get_cell_position returns (row, col)
        rows = [pos[0] for _, pos in selected]
        cols = [pos[1] for _, pos in selected]
        min_r, max_r = min(rows), max(rows)
        min_c, max_c = min(cols), max(cols)
        return self.merge_cells(min_r, min_c, max_r - min_r + 1, max_c - min_c + 1)

    def clear(self) -> None:
        """Reset entire grid to initial empty state."""
        self.merged_cells.clear()
        self.populate_grid()
        logging.info("CollageWidget: grid cleared.")
