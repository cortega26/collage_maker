# widgets/cell.py
"""
Defines the CollageCell widget and ImageMimeData for drag-and-drop.
"""
from typing import Optional
import os
import gc
import logging

from PySide6.QtWidgets import QWidget, QInputDialog
from PySide6.QtCore import (
    Qt, QMimeData, QByteArray, QDataStream, QIODevice, QRect, QSize, QPoint
)
from PySide6.QtGui import (
    QPainter, QPixmap, QImageReader, QColor, QDrag
)

from .. import config
from ..cache import image_cache
from ..optimizer import ImageOptimizer


class ImageMimeData(QMimeData):
    """Custom MIME data for transferring QPixmap and source widget."""
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
    """Individual cell in a CollageWidget grid."""
    def __init__(
        self,
        cell_id: int,
        cell_size: int = config.DEFAULT_CELL_SIZE,
        parent=None
    ):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap: Optional[QPixmap] = None
        self.original_pixmap: Optional[QPixmap] = None
        self.caption = ""
        self.use_caption_formatting = True

        # Default caption formatting
        self.caption_font_size = 14
        self.caption_bold = True
        self.caption_italic = False
        self.caption_underline = False

        # Transformation settings
        self.transformation_mode = Qt.SmoothTransformation
        self.aspect_ratio_mode = Qt.KeepAspectRatio

        # Merge spans
        self.row_span = 1
        self.col_span = 1

        self.setAcceptDrops(True)
        self.setFixedSize(cell_size, cell_size)
        self.setStyleSheet("background-color: transparent;")
        self.selected = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"Collage Cell {cell_id}")

        logging.info("Cell %d created; size %dx%d", cell_id, cell_size, cell_size)

    def setImage(self, pixmap: QPixmap) -> None:
        """Set both display and original pixmap."""
        self.original_pixmap = pixmap
        self.pixmap = pixmap
        self.update()
        logging.info("Cell %d: image set.", self.cell_id)

    def clearImage(self) -> None:
        """Clear image and metadata."""
        self.pixmap = None
        self.original_pixmap = None
        self.caption = ""
        self.update()

    def paintEvent(self, event):
        """Paint placeholder if empty, otherwise image and optional caption."""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.setRenderHint(QPainter.TextAntialiasing)
            if not self.pixmap:
                self._draw_placeholder(painter)
                return
            self._draw_image(painter)
            if self.caption:
                self._draw_caption(painter)
        finally:
            painter.end()

    def _draw_placeholder(self, painter: QPainter) -> None:
        rect = self.rect()
        painter.fillRect(rect, QColor(245, 245, 245))
        painter.setPen(QColor(180, 180, 180))
        font = painter.font(); font.setPointSize(10); painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, "Drop Image Here\nCtrl+Click to Select")

    def _draw_image(self, painter: QPainter) -> None:
        rect = self.rect()
        scaled = self.pixmap.scaled(rect.size(), self.aspect_ratio_mode, self.transformation_mode)
        x = (rect.width() - scaled.width()) // 2
        y = (rect.height() - scaled.height()) // 2
        painter.drawPixmap(QRect(x, y, scaled.width(), scaled.height()), scaled)

    def _draw_caption(self, painter: QPainter) -> None:
        rect = self.rect()
        font = painter.font()
        if self.use_caption_formatting:
            font.setPointSize(self.caption_font_size)
            font.setBold(self.caption_bold)
            font.setItalic(self.caption_italic)
            font.setUnderline(self.caption_underline)
        else:
            font.setPointSize(12)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(self.caption)
        text_rect.moveCenter(QPoint(rect.center().x(), rect.bottom() - text_rect.height()//2 - 5))
        background = text_rect.adjusted(-6, -3, 6, 3)
        painter.fillRect(background, QColor(0, 0, 0, 160))
        painter.setPen(QColor(0, 0, 0, 160))
        painter.drawText(text_rect.translated(1, 1), Qt.AlignCenter, self.caption)
        painter.setPen(Qt.white)
        painter.drawText(text_rect, Qt.AlignCenter, self.caption)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        # Toggle selection
        if event.modifiers() & Qt.ControlModifier:
            self.selected = not self.selected
            self.update()
            logging.info("Cell %d: selected=%s", self.cell_id, self.selected)
            return

        # Begin drag only if image present
        if not self.pixmap:
            return

        drag = QDrag(self)
        mime = ImageMimeData(self.pixmap, self)
        drag.setMimeData(mime)
        preview = self.pixmap.scaled(
            self.width(), self.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        drag.setPixmap(preview)
        drag.exec(Qt.MoveAction)

    def mouseDoubleClickEvent(self, event):
        if not self.pixmap:
            return
        new_caption, ok = QInputDialog.getText(
            self, "Edit Caption", "Enter caption:", text=self.caption
        )
        if ok:
            self.caption = new_caption
            self.update()
            logging.info("Cell %d: caption='%s'", self.cell_id, self.caption)

    def keyPressEvent(self, event):
        """Basic keyboard accessibility: Space toggles selection; Delete clears; Enter edits caption."""
        if event.key() in (Qt.Key_Space,):
            self.selected = not self.selected
            self.update()
            event.accept(); return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.clearImage()
            event.accept(); return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.pixmap:
                self.mouseDoubleClickEvent(None)
                event.accept(); return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # Allow drop on cell as long as data format matches
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        mime = event.mimeData()
        # Internal move
        if mime.hasFormat("application/x-pixmap"):
            source = getattr(mime, 'source_widget', None)
            if source and source is not self:
                self.pixmap, source.pixmap = source.pixmap, self.pixmap
                self.original_pixmap, source.original_pixmap = source.original_pixmap, self.original_pixmap
                self.caption, source.caption = source.caption, self.caption
                self.update(); source.update()
                event.acceptProposedAction()
                return
        # External file drop
        if mime.hasUrls():
            path = mime.urls()[0].toLocalFile()
            if os.path.exists(path):
                self._load_image(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def _load_image(self, file_path: str) -> None:
        """Load, optimize, cache, and display image."""
        try:
            # Cache check
            cached, meta = image_cache.get(file_path)
            if cached:
                self.setImage(cached)
                return

            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            size = reader.size()
            fmt = reader.format().data().decode('utf-8')

            # Unsupported formats
            if fmt.lower() not in config.SUPPORTED_IMAGE_FORMATS:
                raise IOError(f"Unsupported format: {fmt}")

            # Large image scaling
            max_dim = max(size.width(), size.height())
            if max_dim > config.MAX_IMAGE_DIMENSION:
                scale = config.MAX_IMAGE_DIMENSION / max_dim
                reader.setScaledSize(
                    QSize(int(size.width()*scale), int(size.height()*scale))
                )

            img = reader.read()
            if img.isNull():
                raise IOError(f"Failed to read image: {reader.errorString()}")

            # Optimize for display
            optimized = ImageOptimizer.optimize_image(img, self.size())
            pix = QPixmap.fromImage(optimized)
            self.setImage(pix)

            # Cache full-quality
            full_meta = ImageOptimizer.process_metadata(file_path)
            image_cache.put(file_path, pix, full_meta)

        except Exception as e:
            logging.error("Cell %d: load error: %s", self.cell_id, e)

    def optimize_memory(self) -> None:
        """Release cached heavy data when under memory pressure."""
        if self.pixmap and self.original_pixmap:
            disp = self.size()
            orig_size = self.original_pixmap.size()
            if (orig_size.width() > disp.width()*2 or orig_size.height() > disp.height()*2):
                optimized = self.original_pixmap.scaled(
                    disp * 2,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.original_pixmap = optimized
                gc.collect()
