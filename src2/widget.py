# === Module: widget.py ===
"""
Defines CollageWidget: grid management, merging/splitting, animations.
"""
from PySide6.QtWidgets import QWidget, QGridLayout, QLabel
from PySide6.QtCore import QSize, QRect, QPoint
from PySide6.QtGui import QPropertyAnimation, QParallelAnimationGroup, QEasingCurve

from cell import CollageCell

class CollageWidget(QWidget):
    def __init__(self, rows=2, cols=2, cell_size=260, parent=None):
        super().__init__(parent)
        self.rows = rows; self.cols = cols; self.cell_size = cell_size
        self.merged: dict[tuple[int,int], tuple[int,int]] = {}
        self.layout = QGridLayout(self)
        self.layout.setSpacing(2); self.layout.setContentsMargins(0,0,0,0)
        self.cells: list[CollageCell] = []
        self.populate_grid()

    def populate_grid(self):
        # clear existing
        for i in reversed(range(self.layout.count())):
            w = self.layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.cells.clear()
        # create
        for r in range(self.rows):
            for c in range(self.cols):
                idx = r*self.cols + c + 1
                cell = CollageCell(idx, self.cell_size, self)
                self.layout.addWidget(cell, r, c)
                self.cells.append(cell)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        w = self.cols*self.cell_size + (self.cols-1)*self.layout.spacing()
        h = self.rows*self.cell_size + (self.rows-1)*self.layout.spacing()
        return QSize(w,h)

    def get_cell_position(self, cell: CollageCell) -> tuple[int,int] | None:
        idx = self.layout.indexOf(cell)
        if idx < 0: return None
        r,c,rs,cs = self.layout.getItemPosition(idx)
        return (r,c)

    def merge_cells(self, start_row: int, start_col: int, row_span: int, col_span: int) -> bool:
        # split overlapping
        for (mr,mc),(mrs,mcs) in list(self.merged.items()):
            if (mr < start_row+row_span and mr+mrs > start_row and
                mc < start_col+col_span and mc+mcs > start_col):
                self.split_merged_cell(mr,mc)
        # collect
        target = self.get_cell_at(start_row, start_col)
        if not target: return False
        to_merge = [self.get_cell_at(r,c) for r in range(start_row, start_row+row_span)
                    for c in range(start_col, start_col+col_span)
                    if not (r==start_row and c==start_col)]
        for cell in to_merge:
            self.layout.removeWidget(cell); cell.hide(); self.cells.remove(cell)
        self.layout.removeWidget(target)
        self.layout.addWidget(target, start_row, start_col, row_span, col_span)
        target.setFixedSize(
            self.cell_size*col_span + (col_span-1)*self.layout.spacing(),
            self.cell_size*row_span + (row_span-1)*self.layout.spacing()
        )
        self.merged[(start_row,start_col)] = (row_span, col_span)
        self.setFixedSize(self.sizeHint())
        return True

    def split_merged_cell(self, row: int, col: int) -> bool:
        if (row,col) not in self.merged: return False
        row_span, col_span = self.merged.pop((row,col))
        # find merged cell
        merged_cell = self.get_cell_at(row,col)
        pix = merged_cell.pixmap; cap = merged_cell.caption; sel = merged_cell.selected
        self.layout.removeWidget(merged_cell); merged_cell.hide(); self.cells.remove(merged_cell)
        # recreate
        for r in range(row, row+row_span):
            for c in range(col, col+col_span):
                cell = CollageCell(r*self.cols+c+1, self.cell_size, self)
                if r==row and c==col:
                    if pix: cell.set_image(pix)
                    cell.caption = cap; cell.selected = sel
                self.layout.addWidget(cell, r, c)
                self.cells.append(cell)
        self.setFixedSize(self.sizeHint())
        return True

    def get_cell_at(self, row: int, col: int) -> CollageCell | None:
        for i in range(self.layout.count()):
            item = self.layout.itemAt(i); w = item.widget()
            if w:
                r,c,rs,cs = self.layout.getItemPosition(i)
                if r==row and c==col:
                    return w
        return None

    def merge_selected(self):
        pos = [self.get_cell_position(c) for c in self.cells if c.selected]
        if len(pos)<2: return
        rows = [p[0] for p in pos]; cols=[p[1] for p in pos]
        minr,maxr = min(rows), max(rows); minc,maxc=min(cols),max(cols)
        if (maxr-minr+1)*(maxc-minc+1) != len(pos): return
        self.merge_cells(minr,minc,maxr-minr+1, maxc-minc+1)
        for c in self.cells: c.selected=False; c.update()

    def split_selected(self):
        for cell in self.cells:
            if cell.selected:
                pos = self.get_cell_position(cell)
                if pos and pos in self.merged:
                    self.split_merged_cell(*pos)
                    break

    def animate_swap(self, src: CollageCell, tgt: CollageCell):
        sp = src.mapTo(self, QPoint(0,0)); tp = tgt.mapTo(self, QPoint(0,0))
        lab1=src.pixmap and QLabel(self); lab2=tgt.pixmap and QLabel(self)
        if lab1: lab1.setPixmap(src.pixmap);
        if lab2: lab2.setPixmap(tgt.pixmap)
        # ... animation omitted for brevity

    def sanitize_positions(self):
        # ensure consistency
        pass