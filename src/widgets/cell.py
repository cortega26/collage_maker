# widgets/cell.py
"""
Defines the CollageCell widget and ImageMimeData for drag-and-drop.
"""
from typing import Optional
import os
import gc
import logging

from PySide6.QtWidgets import QWidget, QInputDialog, QDialog, QDialogButtonBox, QVBoxLayout, QLabel, QTextEdit
from PySide6.QtCore import (
    Qt, QMimeData, QByteArray, QDataStream, QIODevice, QRect, QSize, QPoint
)
from PySide6.QtGui import (
    QPainter, QPixmap, QImageReader, QColor, QDrag, QAction, QImage,
    QFont, QFontMetrics, QPainterPath, QPen
)
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import QBuffer, QByteArray

from .. import config
from ..cache import get_cache
from ..optimizer import ImageOptimizer
from ..managers.autosave_encoding import AutosaveToken, get_autosave_encoder
from utils.image_operations import apply_filter as pil_apply_filter, adjust_brightness as pil_brightness, adjust_contrast as pil_contrast
from PIL import Image
from io import BytesIO


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
        # Legacy single caption (kept for compatibility)
        self.caption = ""
        # Meme-style captions
        self.top_caption: str = ""
        self.bottom_caption: str = ""
        self.show_top_caption: bool = True
        self.show_bottom_caption: bool = True
        # Caption style (per-cell; can be overridden from UI)
        self.caption_font_family: str = "Impact"
        self.caption_min_size: int = 12
        self.caption_max_size: int = 48
        self.caption_uppercase: bool = True
        self.caption_stroke_width: int = 3
        self.caption_stroke_color: QColor = QColor(0, 0, 0)
        self.caption_fill_color: QColor = QColor(255, 255, 255)
        self.caption_safe_margin_ratio: float = 0.04  # relative to image rect
        # Overflow flags for tooltips
        self._top_caption_overflow: bool = False
        self._bottom_caption_overflow: bool = False
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
        self._selected = False
        self.setProperty('selected', False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"Collage Cell {cell_id}")

        # Autosave payload tracking
        self._autosave_payload: Optional[str] = None
        self._autosave_token: AutosaveToken = (self.cell_id, 0)
        self._autosave_generation: int = 0
        self._autosave_pending: bool = False

        logging.info("Cell %d created; size %dx%d", cell_id, cell_size, cell_size)

    @property
    def selected(self) -> bool:
        return getattr(self, "_selected", False)

    @selected.setter
    def selected(self, value: bool) -> None:
        new_val = bool(value)
        if getattr(self, "_selected", False) == new_val:
            return
        self._selected = new_val
        self.setProperty('selected', new_val)
        style = self.style()
        if style:
            style.unpolish(self)
            style.polish(self)
        self.update()

    def setImage(self, pixmap: QPixmap, *, original: Optional[QPixmap] = None) -> None:
        """Set the display pixmap while preserving an optional original."""
        self.pixmap = pixmap
        if original is not None:
            self.original_pixmap = original
        elif self.original_pixmap is None:
            self.original_pixmap = pixmap
        self.update()
        logging.info("Cell %d: image set.", self.cell_id)
        self._schedule_autosave_encoding(self.original_pixmap or self.pixmap)

    def clearImage(self) -> None:
        """Clear image and metadata."""
        self.pixmap = None
        self.original_pixmap = None
        self.caption = ""
        self.update()
        self._schedule_autosave_encoding(None)

    def paintEvent(self, event):
        """Paint placeholder if empty, otherwise image and optional caption."""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.setRenderHint(QPainter.TextAntialiasing)
            img_rect = None
            self._top_caption_overflow = False
            self._bottom_caption_overflow = False
            if not self.pixmap:
                self._draw_placeholder(painter)
            else:
                img_rect = self._draw_image(painter)
                # Legacy single-caption support
                if self.caption and not self.top_caption and not self.bottom_caption:
                    self._draw_legacy_caption(painter)
                # Meme-style captions
                if self.show_top_caption and self.top_caption:
                    self._top_caption_overflow = self._draw_meme_caption(painter, img_rect, self.top_caption, position="top")
                if self.show_bottom_caption and self.bottom_caption:
                    self._bottom_caption_overflow = self._draw_meme_caption(painter, img_rect, self.bottom_caption, position="bottom")
            # Update tooltip based on overflow (only meaningful when image exists)
            tips = []
            if self._top_caption_overflow:
                tips.append("Top caption too long for image")
            if self._bottom_caption_overflow:
                tips.append("Bottom caption too long for image")
            self.setToolTip("; ".join(tips) if tips else "")
            if self.selected:
                painter.save()
                highlight = QColor(29, 78, 216, 40)  # subtle focus overlay
                painter.setPen(Qt.NoPen)
                painter.setBrush(highlight)
                painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
                pen = QPen(QColor(29, 78, 216))
                pen.setWidth(3)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
                painter.restore()
        finally:
            painter.end()

    def _draw_placeholder(self, painter: QPainter) -> None:
        rect = self.rect()
        painter.fillRect(rect, QColor(245, 245, 245))
        painter.setPen(QColor(180, 180, 180))
        font = painter.font(); font.setPointSize(10); painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, "Drop Image Here\nCtrl+Click to Select")

    def _draw_image(self, painter: QPainter) -> QRect:
        rect = self.rect()
        scaled = self.pixmap.scaled(rect.size(), self.aspect_ratio_mode, self.transformation_mode)
        x = (rect.width() - scaled.width()) // 2
        y = (rect.height() - scaled.height()) // 2
        target = QRect(x, y, scaled.width(), scaled.height())
        painter.drawPixmap(target, scaled)
        return target

    def _draw_legacy_caption(self, painter: QPainter) -> None:
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

    # --- Meme-style caption rendering ---
    def _draw_meme_caption(self, painter: QPainter, image_rect: QRect, text: str, *, position: str) -> bool:
        if not text:
            return False
        t = text.upper() if self.caption_uppercase else text
        # Safe area and area height (30% of image height for captions)
        margin = int(self.caption_safe_margin_ratio * min(image_rect.width(), image_rect.height()))
        area_width = max(1, image_rect.width() - 2 * margin)
        area_height = max(1, int(image_rect.height() * 0.30) - margin)
        if position == "top":
            area_top = image_rect.top() + margin
        else:
            area_top = image_rect.bottom() - margin - area_height
        area_left = image_rect.left() + margin

        # Find font size and wrapped lines that fit
        font, lines, line_spacing, ascent, overflow = self._fit_text(t, area_width, area_height)
        painter.setFont(font)

        # Prepare stroke and fill
        pen = QPen(self.caption_stroke_color)
        pen.setWidth(self.caption_stroke_width)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(self.caption_fill_color)

        metrics = QFontMetrics(font)
        total_text_height = len(lines) * line_spacing - (line_spacing - metrics.ascent())
        y = area_top + max(0, (area_height - total_text_height) // 2) + ascent
        for line in lines:
            w = metrics.horizontalAdvance(line)
            x = area_left + max(0, (area_width - w) // 2)
            path = QPainterPath()
            path.addText(x, y, font, line)
            painter.drawPath(path)
            y += line_spacing
        return overflow

    def _fit_text(self, text: str, max_w: int, max_h: int) -> tuple[QFont, list[str], int, int, bool]:
        """Return (font, lines, line_spacing, ascent) fitting text in area.

        Shrinks from max_size to min_size; wraps by words. On overflow at
        min_size, ellipsizes the last line.
        """
        words = text.split()
        for size in range(self.caption_max_size, self.caption_min_size - 1, -1):
            font = QFont(self.caption_font_family, pointSize=size)
            font.setBold(True)
            metrics = QFontMetrics(font)
            line_spacing = metrics.lineSpacing()
            ascent = metrics.ascent()
            lines: list[str] = []
            line = ""
            for i, w in enumerate(words):
                trial = (line + " " + w).strip()
                if metrics.horizontalAdvance(trial) <= max_w or not line:
                    line = trial
                else:
                    lines.append(line)
                    line = w
            if line:
                lines.append(line)
            total_h = len(lines) * line_spacing
            if total_h <= max_h:
                return font, lines, line_spacing, ascent, False
        # Ellipsize last line at min font
        font = QFont(self.caption_font_family, pointSize=self.caption_min_size)
        font.setBold(True)
        metrics = QFontMetrics(font)
        line_spacing = metrics.lineSpacing()
        ascent = metrics.ascent()
        lines = []
        line = ""
        for i, w in enumerate(words):
            trial = (line + " " + w).strip()
            if metrics.horizontalAdvance(trial + "…") <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = w
        if line:
            # Ensure last line with ellipsis fits
            l = line
            while metrics.horizontalAdvance(l + "…") > max_w and l:
                l = l[:-1]
            lines.append((l + "…") if l else line[: max(0, len(line) - 1)] + "…")
        return font, lines, line_spacing, ascent, True

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        # Toggle selection
        if event.modifiers() & Qt.ControlModifier:
            self.selected = not self.selected
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
            return super().mouseDoubleClickEvent(event)

        if event is None:
            self._edit_top_caption()
            return

        y = event.position().y() if hasattr(event, "position") else event.pos().y()
        if y < self.height() / 2:
            self._edit_top_caption()
        else:
            self._edit_bottom_caption()
        event.accept()

    def keyPressEvent(self, event):
        """Basic keyboard accessibility: Space toggles selection; Delete clears; Enter edits caption."""
        if event.key() in (Qt.Key_Space,):
            self.selected = not self.selected
            event.accept(); return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.clearImage()
            event.accept(); return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.pixmap:
                self._edit_top_caption()
                event.accept(); return
        super().keyPressEvent(event)

    # --- Context menu: filters and adjustments ---
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        clear_action = QAction("Clear Image", self)
        clear_action.triggered.connect(self.clearImage)
        menu.addAction(clear_action)
        if self.pixmap:
            caps = menu.addMenu("Captions")
            et = QAction("Edit Top Caption…", self); et.triggered.connect(self._edit_top_caption); caps.addAction(et)
            eb = QAction("Edit Bottom Caption…", self); eb.triggered.connect(self._edit_bottom_caption); caps.addAction(eb)
            caps.addSeparator()
            st = QAction("Show Top", self, checkable=True); st.setChecked(self.show_top_caption); st.toggled.connect(self._toggle_top)
            sb = QAction("Show Bottom", self, checkable=True); sb.setChecked(self.show_bottom_caption); sb.toggled.connect(self._toggle_bottom)
            caps.addAction(st); caps.addAction(sb)
            filters = menu.addMenu("Filters")
            for name in ["grayscale", "blur", "sharpen", "smooth", "edge_enhance", "detail"]:
                act = QAction(name.capitalize().replace('_', ' '), self)
                act.triggered.connect(lambda _, n=name: self._apply_pil_filter(n))
                filters.addAction(act)
            adj = menu.addMenu("Adjustments")
            brighter = QAction("Brightness +10%", self); brighter.triggered.connect(lambda: self._apply_adjustment('brightness', 1.1))
            darker = QAction("Brightness -10%", self); darker.triggered.connect(lambda: self._apply_adjustment('brightness', 0.9))
            morec = QAction("Contrast +10%", self); morec.triggered.connect(lambda: self._apply_adjustment('contrast', 1.1))
            lessc = QAction("Contrast -10%", self); lessc.triggered.connect(lambda: self._apply_adjustment('contrast', 0.9))
            for a in (brighter, darker, morec, lessc):
                adj.addAction(a)
        menu.exec(event.globalPos())

    def _prompt_multiline(self, title: str, label_text: str, initial: str) -> Optional[str]:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(label_text))
        edit = QTextEdit(); edit.setPlainText(initial or ""); edit.setMinimumHeight(100)
        v.addWidget(edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec() == QDialog.Accepted:
            return edit.toPlainText()
        return None

    def _edit_top_caption(self) -> None:
        text = self._prompt_multiline("Top Caption", "Enter top caption:", self.top_caption)
        if text is not None:
            self.top_caption = text
            self.show_top_caption = bool(text.strip())
            self.update()

    def _edit_bottom_caption(self) -> None:
        text = self._prompt_multiline("Bottom Caption", "Enter bottom caption:", self.bottom_caption)
        if text is not None:
            self.bottom_caption = text
            self.show_bottom_caption = bool(text.strip())
            self.update()

    def _toggle_top(self, checked: bool) -> None:
        self.show_top_caption = checked
        self.update()

    def _toggle_bottom(self, checked: bool) -> None:
        self.show_bottom_caption = checked
        self.update()

    def _qimage_to_pil(self) -> Image.Image:
        img = self.pixmap.toImage()
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        img.save(buffer, 'PNG')
        pil_img = Image.open(BytesIO(buffer.data()))
        pil_img.load()
        return pil_img

    def _pil_to_qpixmap(self, pil_img: Image.Image) -> QPixmap:
        out = BytesIO()
        pil_img.save(out, format='PNG')
        ba = QByteArray(out.getvalue())
        qimg = QImage.fromData(ba, 'PNG')
        return QPixmap.fromImage(qimg)

    def _apply_pil_filter(self, name: str) -> None:
        try:
            if not self.pixmap:
                return
            pil_img = self._qimage_to_pil()
            result = pil_apply_filter(pil_img, name)
            new_pix = self._pil_to_qpixmap(result)
            self.setImage(new_pix)
        except Exception as e:
            logging.error("Cell %d: filter '%s' failed: %s", self.cell_id, name, e)

    def _apply_adjustment(self, kind: str, factor: float) -> None:
        try:
            if not self.pixmap:
                return
            pil_img = self._qimage_to_pil()
            if kind == 'brightness':
                result = pil_brightness(pil_img, factor)
            elif kind == 'contrast':
                result = pil_contrast(pil_img, factor)
            else:
                return
            new_pix = self._pil_to_qpixmap(result)
            self.setImage(new_pix)
        except Exception as e:
            logging.error("Cell %d: adjustment '%s' failed: %s", self.cell_id, kind, e)

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
                self._schedule_autosave_encoding(self.original_pixmap or self.pixmap)
                source._schedule_autosave_encoding(source.original_pixmap or source.pixmap)
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
            cache_key = self._cache_key(file_path)
            cached, meta = get_cache().get(cache_key)
            if cached:
                if isinstance(cached, tuple) and len(cached) == 2:
                    display_pix, original_pix = cached
                else:
                    display_pix, original_pix = cached, None
                self.setImage(display_pix, original=original_pix)
                return

            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            size = reader.size()
            raw_fmt = reader.format().data() if reader.format() else None
            fmt = raw_fmt.decode('utf-8') if raw_fmt else ''

            # Unsupported formats
            if fmt.lower() not in config.SUPPORTED_IMAGE_FORMATS:
                raise IOError(f"Unsupported image format: '{fmt or 'unknown'}'")

            # Large image scaling
            max_dim = max(size.width(), size.height())
            if max_dim > config.MAX_IMAGE_DIMENSION:
                scale = config.MAX_IMAGE_DIMENSION / max_dim
                reader.setScaledSize(
                    QSize(int(size.width()*scale), int(size.height()*scale))
                )

            img = reader.read()
            if img.isNull() or img.width() <= 0 or img.height() <= 0:
                err = reader.errorString() or "Invalid or empty image data"
                raise IOError(f"Failed to read image: {err}")

            # Optimize for display
            original_pix = QPixmap.fromImage(img)
            optimized = ImageOptimizer.optimize_image(img, self.size())
            display_pix = QPixmap.fromImage(optimized)
            self.setImage(display_pix, original=original_pix)

            # Cache full-quality
            full_meta = ImageOptimizer.process_metadata(file_path)
            get_cache().put(cache_key, (display_pix, original_pix), full_meta)

        except FileNotFoundError as e:
            logging.error("Cell %d: file not found: %s", self.cell_id, file_path)
        except Exception as e:
            logging.error("Cell %d: load error: %s", self.cell_id, e)

    def _cache_key(self, file_path: str) -> str:
        size = self.size()
        return f"{file_path}::{size.width()}x{size.height()}"

    def optimize_memory(self) -> None:
        """Release cached heavy data when under memory pressure."""
        if not self.pixmap:
            return
        disp = self.size()
        pix_size = self.pixmap.size()
        if (pix_size.width() > disp.width()*2 or pix_size.height() > disp.height()*2):
            self.pixmap = self.pixmap.scaled(
                disp * 2,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.update()
            gc.collect()
            self._schedule_autosave_encoding(self.original_pixmap or self.pixmap)

    @property
    def autosave_payload(self) -> Optional[str]:
        """Return the cached autosave payload if available."""
        return self._autosave_payload

    def set_autosave_payload(self, payload: Optional[str]) -> None:
        """Set the cached autosave payload (used when restoring state)."""
        self._autosave_payload = payload
        self._autosave_pending = False

    def _schedule_autosave_encoding(self, pixmap: Optional[QPixmap]) -> None:
        """Start background encoding for the given pixmap."""
        self._autosave_generation += 1
        self._autosave_token = (self.cell_id, self._autosave_generation)
        self._autosave_payload = None
        self._autosave_pending = False
        if pixmap is None:
            return
        image = pixmap.toImage()
        if image.isNull():
            return
        self._autosave_pending = True
        encoder = get_autosave_encoder()
        encoder.encode(self._autosave_token, image, self._handle_autosave_result)

    def _handle_autosave_result(self, token: AutosaveToken, payload: Optional[str]) -> None:
        """Receive encoded payloads from the background encoder."""
        if token != self._autosave_token:
            return
        self._autosave_pending = False
        if payload is None:
            logging.warning("Cell %d: autosave encoding failed", self.cell_id)
            self._autosave_payload = None
            return
        self._autosave_payload = payload
