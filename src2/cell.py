# === Module: cell.py ===
"""
Defines CollageCell: individual grid cell with drag-drop, image loading, caption.
"""
from PySide6.QtWidgets import QWidget, QMessageBox, QInputDialog
from PySide6.QtGui import QPixmap, QPainter, QColor, QDrag, QImageReader
from PySide6.QtCore import Qt, QMimeData, QByteArray, QDataStream, QIODevice, QRect, QSize, QPoint

from cache import image_cache
from optimizer import ImageOptimizer

class ImageMimeData(QMimeData):
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
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.setAcceptDrops(True)
        self.setFixedSize(cell_size, cell_size)
        self.pixmap: QPixmap = None
        self.original_pixmap: QPixmap = None
        self.caption: str = ""
        self.selected: bool = False

    def set_image(self, pixmap: QPixmap):
        self.original_pixmap = pixmap
        self.pixmap = pixmap
        self.update()

    def clear_image(self):
        self.pixmap = None
        self.original_pixmap = None
        self.caption = ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing
        )
        rect = self.rect()
        if self.selected:
            pen = painter.pen()
            pen.setColor(QColor(52, 152, 219))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1,1,-1,-1))
        if self.pixmap:
            scaled = self.pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            if self.caption:
                font = painter.font()
                font.setPointSize(12)
                painter.setFont(font)
                painter.setPen(Qt.white)
                painter.drawText(rect.adjusted(4,4,-4,-4), Qt.AlignBottom|Qt.AlignHCenter, self.caption)
        else:
            painter.fillRect(rect, QColor(245,245,245))
            painter.setPen(QColor(180,180,180))
            painter.drawText(rect, Qt.AlignCenter, "Drop Image Here")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.selected and event.modifiers() == Qt.ControlModifier:
                self.selected = False
                self.update()
                return
            if event.modifiers() == Qt.ControlModifier:
                self.selected = True
                self.update()
                return
            if self.pixmap:
                drag = QDrag(self)
                mime = ImageMimeData(self.pixmap, self)
                drag.setMimeData(mime)
                preview = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(preview)
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
            src = mime.source_widget
            if src and src is not self:
                # swap
                self.pixmap, src.pixmap = src.pixmap, self.pixmap
                self.original_pixmap, src.original_pixmap = src.original_pixmap, self.original_pixmap
                self.caption, src.caption = src.caption, self.caption
                self.update(); src.update()
                event.acceptProposedAction()
                return
        if mime.hasUrls():
            path = mime.urls()[0].toLocalFile()
            self._load_external(path)
            event.acceptProposedAction()
            return
        event.ignore()

    def _load_external(self, path: str):
        try:
            pix, _ = image_cache.get(path)
            if pix:
                self.set_image(pix)
                return
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            img = reader.read()
            if img.isNull():
                raise ValueError(reader.errorString())
            optimized = ImageOptimizer.optimize_image(img, self.size())
            pixmap = QPixmap.fromImage(optimized)
            self.set_image(pixmap)
            meta = ImageOptimizer.extract_metadata(path)
            image_cache.put(path, pixmap, meta)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", str(e))

    def cleanup(self):
        self.pixmap = None
        self.original_pixmap = None

    def optimize_memory(self):
        # placeholder for memory reduce logic
        pass

    def batch_process_images(self, paths: list[str]):
        from workers import BatchProcessor
        BatchProcessor(self).process_files(paths, self.size())
