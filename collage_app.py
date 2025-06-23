import sys
import logging
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QSpinBox,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QInputDialog,
    QCheckBox,
    QLabel,
    QColorDialog,
)
from PySide6.QtCore import (
    Qt,
    QMimeData,
    QByteArray,
    QDataStream,
    QIODevice,
    QRect,
    QSize,
    QPoint,
)
from PySide6.QtGui import QDrag, QPixmap, QPainter, QImageReader, QColor

# Simple logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ImageMimeData(QMimeData):
    """Mime data container used for internal drag & drop."""
    def __init__(self, pixmap: QPixmap, source_widget: "CollageCell"):
        super().__init__()
        self._pixmap = pixmap
        self.source_widget = source_widget
        ba = QByteArray()
        stream = QDataStream(ba, QIODevice.WriteOnly)
        stream << pixmap.toImage()
        self.setData("application/x-pixmap", ba)

    def image(self) -> QPixmap:
        return self._pixmap

class CollageCell(QWidget):
    """Square widget that displays an image and optional caption."""
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap: QPixmap | None = None
        self.caption = ""
        self.font_size = 14
        self.bold = True
        self.italic = True
        self.underline = True
        self.color = QColor("yellow")
        self.setAcceptDrops(True)
        self.setFixedSize(cell_size, cell_size)
        self.setStyleSheet("background-color: transparent;")
        self.row = 0
        self.col = 0
        self.row_span = 1
        self.col_span = 1
        self.merged_children: list[CollageCell] = []
        self.selected = False

    def setImage(self, pixmap: QPixmap):
        self.pixmap = pixmap
        self.update()

    def clearImage(self):
        self.pixmap = None
        self.caption = ""
        self.update()

    def _draw_caption(self, painter: QPainter, rect: QRect):
        if not self.caption:
            return
        font = painter.font()
        font.setPointSize(self.font_size)
        font.setBold(self.bold)
        font.setItalic(self.italic)
        font.setUnderline(self.underline)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(self.caption)
        text_rect.moveCenter(QPoint(rect.center().x(), rect.bottom() - text_rect.height() // 2 - 5))
        bg_rect = text_rect.adjusted(-4, -2, 4, 2)
        painter.fillRect(bg_rect, QColor(0, 0, 0, 150))
        painter.setPen(self.color)
        painter.drawText(text_rect, Qt.AlignCenter, self.caption)

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()
        if self.pixmap:
            scaled = self.pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(QRect(x, y, scaled.width(), scaled.height()), scaled)
            self._draw_caption(painter, rect)
        else:
            painter.fillRect(rect, Qt.white)
            painter.setPen(Qt.gray)
            painter.drawText(rect, Qt.AlignCenter, "Drop Image Here")
        if self.selected:
            painter.setPen(QColor("red"))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.selected = not self.selected
            self.update()
            return
        if event.button() == Qt.LeftButton and self.pixmap:
            drag = QDrag(self)
            mime_data = ImageMimeData(self.pixmap, self)
            drag.setMimeData(mime_data)
            drag.setPixmap(self.pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            drag.exec(Qt.MoveAction)

    def mouseDoubleClickEvent(self, event):
        if self.pixmap:
            text, ok = QInputDialog.getText(self, "Edit Caption", "Caption:", text=self.caption)
            if ok:
                self.caption = text
                self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-pixmap"):
            source = getattr(mime, "source_widget", None)
            if source and source is not self:
                self.pixmap, source.pixmap = source.pixmap, self.pixmap
                self.caption, source.caption = source.caption, self.caption
                self.update()
                source.update()
                event.acceptProposedAction()
                return
        elif mime.hasUrls():
            file_path = mime.urls()[0].toLocalFile()
            if file_path:
                reader = QImageReader(file_path)
                image = reader.read()
                if not image.isNull():
                    self.setImage(QPixmap.fromImage(image))
                    event.acceptProposedAction()
                    return
        event.ignore()

class CollageWidget(QWidget):
    """Grid container for CollageCell widgets."""
    def __init__(self, rows=2, columns=2, cell_size=260, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.cell_size = cell_size
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(2)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.grid_layout)
        self.cells: list[CollageCell] = []
        self.populate_grid()
        self.setFixedSize(self.idealSize())

    def cell_at(self, row: int, col: int) -> CollageCell | None:
        index = row * self.columns + col
        if 0 <= index < len(self.cells):
            return self.cells[index]
        return None

    def unmerge_all(self):
        for cell in self.cells:
            if cell.merged_children:
                self.unmerge_cell(cell)

    def unmerge_cell(self, cell: CollageCell):
        if not cell.merged_children:
            return
        self.grid_layout.removeWidget(cell)
        self.grid_layout.addWidget(cell, cell.row, cell.col, 1, 1)
        for child in cell.merged_children:
            self.grid_layout.addWidget(child, child.row, child.col, 1, 1)
            child.show()
        cell.row_span = cell.col_span = 1
        cell.merged_children = []
        cell.update()

    def merge_selected(self):
        selected = [c for c in self.cells if c.selected]
        if len(selected) < 2:
            return
        rows = {c.row for c in selected}
        cols = {c.col for c in selected}
        r0, r1 = min(rows), max(rows)
        c0, c1 = min(cols), max(cols)
        if len(rows) * len(cols) != len(selected):
            return
        main_cell = self.cell_at(r0, c0)
        if not main_cell or main_cell.merged_children:
            return
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cell = self.cell_at(r, c)
                if not cell or cell.selected is False or cell.merged_children:
                    return
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cell = self.cell_at(r, c)
                if cell is main_cell:
                    continue
                self.grid_layout.removeWidget(cell)
                cell.hide()
                main_cell.merged_children.append(cell)
        main_cell.row_span = r1 - r0 + 1
        main_cell.col_span = c1 - c0 + 1
        self.grid_layout.addWidget(main_cell, r0, c0, main_cell.row_span, main_cell.col_span)
        for cell in selected:
            cell.selected = False
            cell.update()

    def unmerge_selected(self):
        for cell in [c for c in self.cells if c.selected and c.merged_children]:
            self.unmerge_cell(cell)
            cell.selected = False
            cell.update()

    def idealSize(self) -> QSize:
        width = self.columns * self.cell_size + (self.columns - 1) * 2
        height = self.rows * self.cell_size + (self.rows - 1) * 2
        return QSize(width, height)

    def populate_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.cells = []
        for i in range(self.rows):
            for j in range(self.columns):
                cell_id = i * self.columns + j + 1
                cell = CollageCell(cell_id, self.cell_size, self)
                cell.row = i
                cell.col = j
                self.grid_layout.addWidget(cell, i, j)
                self.cells.append(cell)


    def update_grid(self, rows: int, columns: int, cell_size: int | None = None):
        self.unmerge_all()
        if cell_size is not None:
            self.cell_size = cell_size
        self.rows = rows
        self.columns = columns
        if rows * columns == len(self.cells):
            while self.grid_layout.count():
                self.grid_layout.takeAt(0)
            for index, cell in enumerate(self.cells):
                i, j = divmod(index, columns)
                cell.row = i
                cell.col = j
                cell.setFixedSize(self.cell_size, self.cell_size)

                self.grid_layout.addWidget(cell, i, j)
        else:
            self.populate_grid()
        self.setFixedSize(self.idealSize())

    def save_collage(self, file_path: str) -> bool:
        pixmap = self.grab()
        return pixmap.save(file_path)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker")
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addLayout(self._create_controls())
        self.collage = CollageWidget()
        layout.addWidget(self.collage, alignment=Qt.AlignCenter)

    def _create_controls(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.rows_spin = QSpinBox(minimum=1, value=2, prefix="Rows: ")
        self.cols_spin = QSpinBox(minimum=1, value=2, prefix="Cols: ")
        self.size_spin = QSpinBox(minimum=50, maximum=500, value=260, prefix="Size: ")
        update_btn = QPushButton("Update")
        update_btn.clicked.connect(self._update_collage)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_collage)
        merge_btn = QPushButton("Merge")
        merge_btn.clicked.connect(self._merge_cells)
        unmerge_btn = QPushButton("Unmerge")
        unmerge_btn.clicked.connect(self._unmerge_cells)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_collage)
        layout.addWidget(self.rows_spin)
        layout.addWidget(self.cols_spin)
        layout.addWidget(self.size_spin)
        layout.addWidget(update_btn)
        layout.addWidget(save_btn)
        layout.addWidget(merge_btn)
        layout.addWidget(unmerge_btn)
        layout.addWidget(clear_btn)
        layout.addStretch()
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 36)
        self.font_spin.setValue(14)

        self.font_spin.valueChanged.connect(self._apply_format)
        self.bold_chk = QCheckBox("Bold")
        self.bold_chk.setChecked(True)
        self.bold_chk.toggled.connect(self._apply_format)
        self.italic_chk = QCheckBox("Italic")
        self.italic_chk.setChecked(True)
        self.italic_chk.toggled.connect(self._apply_format)
        self.underline_chk = QCheckBox("Underline")
        self.underline_chk.setChecked(True)
        self.underline_chk.toggled.connect(self._apply_format)
        self.color_btn = QPushButton("Color")
        self.color_btn.clicked.connect(self._choose_color)
        for w in [self.font_spin, self.bold_chk, self.italic_chk, self.underline_chk, self.color_btn]:
            layout.addWidget(w)

        layout.addWidget(QLabel("Right-click cells to select"))

        self.color = QColor("yellow")
        return layout

    def _choose_color(self):
        color = QColorDialog.getColor(self.color, self, "Caption Color")
        if color.isValid():
            self.color = color
            self._apply_format()

    def _apply_format(self):
        for cell in self.collage.cells:
            cell.font_size = self.font_spin.value()
            cell.bold = self.bold_chk.isChecked()
            cell.italic = self.italic_chk.isChecked()
            cell.underline = self.underline_chk.isChecked()
            cell.color = self.color
            cell.update()

    def _update_collage(self):
        self.collage.update_grid(
            self.rows_spin.value(),
            self.cols_spin.value(),
            self.size_spin.value(),
        )
        self._apply_format()

    def _merge_cells(self):
        self.collage.merge_selected()

    def _unmerge_cells(self):
        self.collage.unmerge_selected()

    def _clear_collage(self):
        self.collage.unmerge_all()

        for cell in self.collage.cells:
            cell.clearImage()

    def _save_collage(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Collage", "", "PNG Files (*.png);;JPEG Files (*.jpg)")
        if file_path:
            if self.collage.save_collage(file_path):
                logger.info("Collage saved to %s", file_path)
            else:
                logger.error("Failed to save collage")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
