# main.py
"""
Entry point and main application window for Collage Maker.
"""
import sys
import os
import logging

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QFileDialog, QMessageBox,
    QDialog, QSlider, QDialogButtonBox, QCheckBox, QComboBox,
    QFrame, QSizePolicy, QPlainTextEdit, QFontComboBox, QColorDialog
)
from PySide6.QtCore import Qt, QPoint, QStandardPaths
from PySide6.QtGui import QPainter, QPixmap, QKeySequence, QShortcut, QImage, QImageReader
from dataclasses import dataclass

from pathlib import Path
try:
    # Preferred package-relative imports
    from . import config, style_tokens
    from .widgets.collage import CollageWidget
    from .managers.autosave import AutosaveManager
    from .managers.performance import PerformanceMonitor
    from .managers.recovery import ErrorRecoveryManager
    from .optimizer import ImageOptimizer
except ImportError:
    # Fallback for running `python src/main.py` directly
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import config, style_tokens
    from src.widgets.collage import CollageWidget
    from src.managers.autosave import AutosaveManager
    from src.managers.performance import PerformanceMonitor
    from src.managers.recovery import ErrorRecoveryManager
    from src.optimizer import ImageOptimizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler("collage_maker.log"),
        logging.StreamHandler(sys.stdout)
    ]
)


def global_exception_handler(exc_type, value, tb):
    logging.error("Uncaught exception", exc_info=(exc_type, value, tb))
    sys.__excepthook__(exc_type, value, tb)


sys.excepthook = global_exception_handler


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker - PySide6")
        self.resize(900, 700)

        # Central widget and layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        # Compact outer margins/spacing
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(8)

        # Determine theme colors for per-widget overrides
        self._theme = os.environ.get('COLLAGE_THEME', 'light')
        self._colors = style_tokens.get_colors(theme=self._theme)

        # Controls and collage
        topbar = self._create_controls_bar()
        main_layout.addWidget(topbar)
        # Separator under the toolbar (thin)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)
        # Caption tools
        self.caption_panel = self._create_caption_panel()
        main_layout.addWidget(self.caption_panel)
        self.collage = CollageWidget(
            rows=self.rows_spin.value(),
            columns=self.cols_spin.value(),
            cell_size=config.DEFAULT_CELL_SIZE
        )
        self.collage.setAccessibleName("Collage Grid")
        # Wrap in a 'card' frame that uses design tokens
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(self.collage, alignment=Qt.AlignCenter)
        main_layout.addWidget(card)

        # Managers
        self.autosave = AutosaveManager(self, self.get_collage_state)
        self.performance = PerformanceMonitor(self)
        self.error_recovery = ErrorRecoveryManager(
            self,
            save_state=self.get_collage_state,
            reset_callback=self._reset_collage
        )

        # Shortcuts
        self._create_shortcuts()

        logging.info("MainWindow initialized.")

    def _create_controls_bar(self) -> QWidget:
        bar = QWidget()
        # Set compact property BEFORE creating children so QSS attribute selectors match descendants
        bar.setProperty("compact", "true")
        bar_layout = QHBoxLayout(bar)
        # Extra compact toolbar margins/spacing
        bar_layout.setContentsMargins(4, 2, 4, 2)
        bar_layout.setSpacing(4)
        # Force the toolbar to stay short
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bar.setMaximumHeight(30)

        # Grid controls
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 10)
        self.rows_spin.setValue(config.DEFAULT_ROWS)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 10)
        self.cols_spin.setValue(config.DEFAULT_COLUMNS)
        spin_ss = f"""
        QSpinBox {{
            background-color: {self._colors.surface};
            color: {self._colors.text};
            /* Input border color/thickness */
            border: 1px solid {self._colors.border};
            /* Corner radius (px) */
            border-radius: 6px;
            /* Padding: top right bottom left (px) */
            padding: 2px 14px 2px 6px;\n            /* Min height (px) */ min-height: 22px;
        }}
        QSpinBox QLineEdit {{
            background: transparent;
            color: {self._colors.text};
            selection-background-color: {self._colors.focus};
            selection-color: #ffffff;
        }}
        QSpinBox:disabled {{ color: {self._colors.text_muted}; }}
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            background: {self._colors.surface};
            border-left: 1px solid {self._colors.border};
            width: 22px;
        }}
        """
        self.rows_spin.setStyleSheet(spin_ss)
        self.cols_spin.setStyleSheet(spin_ss)
        self.rows_spin.setAccessibleName("Rows")
        self.cols_spin.setAccessibleName("Columns")

        # Left group
        left = QWidget()
        left_l = QHBoxLayout(left)
        left.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(4)
        rows_label = QLabel("Rows:")
        cols_label = QLabel("Cols:")
        # Fix vertical size of label + spinboxes for a thin toolbar
        for w in (rows_label, cols_label, self.rows_spin, self.cols_spin):
            if hasattr(w, 'setFixedHeight'):
                w.setFixedHeight(22)
            if hasattr(w, 'setSizePolicy'):
                w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        left_l.addWidget(rows_label)
        left_l.addWidget(self.rows_spin)
        left_l.addWidget(cols_label)
        left_l.addWidget(self.cols_spin)
        tmpl_label = QLabel("Templates:")
        tmpl = QComboBox()
        tmpl.addItems(["2x2", "3x3", "2x3", "3x2", "4x4"])
        tmpl.setAccessibleName("Templates")
        tmpl.setToolTip("Choose a grid template")
        tmpl.currentTextChanged.connect(self._apply_template)
        tmpl.setFixedHeight(22)
        tmpl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        left_l.addWidget(tmpl_label)
        left_l.addWidget(tmpl)
        update_btn = QPushButton("Update Grid")
        update_btn.clicked.connect(self._update_grid)
        update_btn.setAccessibleName("Update Grid")
        update_btn.setToolTip("Apply rows/cols to rebuild the grid")
        update_btn.setFixedHeight(22)
        update_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        left_l.addWidget(update_btn)

        # Right group
        right = QWidget()
        right_l = QHBoxLayout(right)
        right.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(4)
        add_btn = QPushButton("Add Images…")
        add_btn.clicked.connect(self._add_images)
        add_btn.setToolTip("Add images to empty cells")
        add_btn.setAccessibleName("Add Images")
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._reset_collage)
        clear_btn.setToolTip("Clear all images and merges")
        clear_btn.setAccessibleName("Clear All")
        save_btn = QPushButton("Save Collage")
        save_btn.clicked.connect(self._show_save_dialog)
        save_btn.setToolTip("Export the collage to PNG/JPEG/WEBP")
        save_btn.setAccessibleName("Save Collage")
        for b in (add_btn, clear_btn, save_btn):
            b.setFixedHeight(22)
            b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            right_l.addWidget(b)

        bar_layout.addWidget(left)
        bar_layout.addStretch(1)
        bar_layout.addWidget(right)
        return bar

    # --- Caption Panel ---

    def _create_caption_panel(self):
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        # Text inputs
        self.top_edit = QPlainTextEdit()
        self.top_edit.setPlaceholderText("Top Caption")
        self.bottom_edit = QPlainTextEdit()
        self.bottom_edit.setPlaceholderText("Bottom Caption")
        self.top_edit.setFixedHeight(48)
        self.bottom_edit.setFixedHeight(48)
        layout.addWidget(QLabel("Top:"))
        layout.addWidget(self.top_edit)
        layout.addWidget(QLabel("Bottom:"))
        layout.addWidget(self.bottom_edit)

        # Visibility toggles
        self.top_visible_chk = QCheckBox("Show Top")
        self.top_visible_chk.setChecked(True)
        self.bottom_visible_chk = QCheckBox("Show Bottom")
        self.bottom_visible_chk.setChecked(True)
        layout.addWidget(self.top_visible_chk)
        layout.addWidget(self.bottom_visible_chk)

        # Style controls (shared)
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentText("Impact")
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(6, 64)
        self.min_size_spin.setValue(12)
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(8, 128)
        self.max_size_spin.setValue(48)
        self.stroke_width_spin = QSpinBox()
        self.stroke_width_spin.setRange(0, 16)
        self.stroke_width_spin.setValue(3)
        self.uppercase_chk = QCheckBox("UPPERCASE")
        self.uppercase_chk.setChecked(True)
        self.stroke_btn = QPushButton("Stroke Color")
        self.fill_btn = QPushButton("Fill Color")
        layout.addWidget(QLabel("Font:"))
        layout.addWidget(self.font_combo)
        layout.addWidget(QLabel("Min:"))
        layout.addWidget(self.min_size_spin)
        layout.addWidget(QLabel("Max:"))
        layout.addWidget(self.max_size_spin)
        layout.addWidget(QLabel("Stroke:"))
        layout.addWidget(self.stroke_width_spin)
        layout.addWidget(self.stroke_btn)
        layout.addWidget(self.fill_btn)
        layout.addWidget(self.uppercase_chk)

        # Debounce timer for live preview
        from PySide6.QtCore import QTimer
        self.caption_timer = QTimer(self)
        self.caption_timer.setSingleShot(True)
        self.caption_timer.setInterval(150)
        self.caption_timer.timeout.connect(self._apply_captions_now)

        # Wire inputs
        self.top_edit.textChanged.connect(lambda: self.caption_timer.start())
        self.bottom_edit.textChanged.connect(
            lambda: self.caption_timer.start())
        self.top_visible_chk.toggled.connect(
            lambda _: self._apply_captions_now())
        self.bottom_visible_chk.toggled.connect(
            lambda _: self._apply_captions_now())
        self.font_combo.currentFontChanged.connect(
            lambda _: self._apply_captions_now())
        for sp in (self.min_size_spin, self.max_size_spin, self.stroke_width_spin):
            sp.valueChanged.connect(lambda _: self._apply_captions_now())
        self.uppercase_chk.toggled.connect(
            lambda _: self._apply_captions_now())
        self.stroke_btn.clicked.connect(lambda: self._pick_color('stroke'))
        self.fill_btn.clicked.connect(lambda: self._pick_color('fill'))

        # Shortcuts
        QShortcut(QKeySequence("T"), self,
                  activated=lambda: self.top_edit.setFocus())
        QShortcut(QKeySequence("B"), self,
                  activated=lambda: self.bottom_edit.setFocus())
        QShortcut(QKeySequence("Ctrl+Return"), self,
                  activated=self._apply_captions_now)

        return panel

    def _pick_color(self, which: str):
        col = QColorDialog.getColor(parent=self)
        if not col.isValid():
            return
        # Apply to selection immediately
        for cell in [c for c in self.collage.cells if getattr(c, 'selected', False)]:
            if which == 'stroke':
                cell.caption_stroke_color = col
            else:
                cell.caption_fill_color = col
            cell.update()

    def _apply_captions_now(self):
        top_text = self.top_edit.toPlainText()
        bottom_text = self.bottom_edit.toPlainText()
        show_top = self.top_visible_chk.isChecked()
        show_bottom = self.bottom_visible_chk.isChecked()
        family = self.font_combo.currentFont().family()
        min_sz = self.min_size_spin.value()
        max_sz = self.max_size_spin.value()
        stroke_w = self.stroke_width_spin.value()
        upper = self.uppercase_chk.isChecked()
        for cell in [c for c in self.collage.cells if getattr(c, 'selected', False)]:
            cell.top_caption = top_text
            cell.bottom_caption = bottom_text
            cell.show_top_caption = show_top
            cell.show_bottom_caption = show_bottom
            cell.caption_font_family = family
            cell.caption_min_size = min_sz
            cell.caption_max_size = max_sz
            cell.caption_stroke_width = stroke_w
            cell.caption_uppercase = upper
            cell.update()

    def _create_shortcuts(self):
        QShortcut(QKeySequence(config.SAVE_SHORTCUT),
                  self, activated=self._show_save_dialog)
        QShortcut(QKeySequence(config.SAVE_ORIGINAL_SHORTCUT), self,
                  activated=lambda: self._show_save_dialog(default_original=True))
        QShortcut(QKeySequence.Undo, self, activated=self._undo)
        QShortcut(QKeySequence.Redo, self, activated=self._redo)
        QShortcut(QKeySequence.SelectAll, self, activated=self._select_all)
        QShortcut(QKeySequence.Delete, self, activated=self._delete_selected)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._add_images)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self,
                  activated=self._reset_collage)

    def _update_grid(self):
        self.collage.update_grid(
            self.rows_spin.value(), self.cols_spin.value())

    def _apply_template(self, name: str):
        try:
            r, c = name.split("x")
            self.rows_spin.setValue(int(r))
            self.cols_spin.setValue(int(c))
            self._update_grid()
        except Exception:
            pass

    def _reset_collage(self):
        self.collage.clear()

    def _undo(self):
        # Unimplemented: placeholder for undo stack
        pass

    def _redo(self):
        pass

    def _select_all(self):
        for cell in self.collage.cells:
            cell.selected = True
            cell.update()

    def _delete_selected(self):
        for cell in self.collage.cells:
            if cell.selected:
                cell.clearImage()

    def _show_save_dialog(self, default_original: bool = False):
        opts = self._prompt_save_options(default_original)
        if not opts:
            return
        self._export_collage(opts)

    def _export_collage(self, opts: 'MainWindow.SaveOptions'):
        try:
            path = self._select_save_path(opts.format)
            if not path:
                return
            primary = self._render_scaled_pixmap(opts.resolution)
            if opts.format in ('jpeg', 'jpg'):
                primary = self._convert_for_jpeg(primary)
            # Add basic metadata for accessibility/compatibility
            img = primary.toImage()
            img.setText("Software", "Collage Maker")
            img.save(path, opts.format, opts.quality)
            logging.info("Saved collage to %s", path)

            if opts.save_original:
                orig_path = os.path.splitext(
                    path)[0] + '_original.' + opts.format
                self._save_original(orig_path, opts.format, opts.quality)

            QMessageBox.information(self, "Saved", f"Saved: {path}")
        except Exception as e:
            logging.error("Save failed: %s", e)
            QMessageBox.critical(self, "Error", f"Could not save collage: {e}")

    @dataclass(slots=True)
    class SaveOptions:
        format: str
        quality: int
        resolution: int
        save_original: bool

    def _prompt_save_options(self, default_original: bool = False) -> 'MainWindow.SaveOptions | None':
        dialog = QDialog(self)
        dialog.setWindowTitle("Save Collage")
        v = QVBoxLayout(dialog)

        preview = QLabel()
        pix = self.collage.grab().scaled(
            300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        preview.setPixmap(pix)
        v.addWidget(preview, alignment=Qt.AlignCenter)

        original = QCheckBox("Save Original at full resolution")
        original.setChecked(default_original)
        v.addWidget(original)

        fmt_box = QComboBox()
        fmt_box.addItems(["PNG", "JPEG", "WEBP"])
        v.addWidget(fmt_box)

        v.addWidget(QLabel("Quality / Compression:"))
        quality = QSlider(Qt.Horizontal)
        quality.setRange(config.QUALITY_MIN, config.QUALITY_MAX)
        quality.setValue(config.QUALITY_DEFAULT)
        v.addWidget(quality)

        v.addWidget(QLabel("Resolution:"))
        res_box = QComboBox()
        res_box.addItems([f"{m}x" for m in config.RESOLUTION_MULTIPLIERS])
        v.addWidget(res_box)

        btns = QDialogButtonBox(QDialogButtonBox.Save |
                                QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        v.addWidget(btns)

        if dialog.exec() != QDialog.Accepted:
            return None
        return MainWindow.SaveOptions(
            format=fmt_box.currentText().lower(),
            quality=quality.value(),
            resolution=int(res_box.currentText().rstrip('x')),
            save_original=original.isChecked(),
        )

    def _select_save_path(self, fmt: str) -> 'str | None':
        options = QFileDialog.Options()
        if sys.platform.startswith('win'):
            options |= QFileDialog.DontUseNativeDialog
        pictures_dir = QStandardPaths.writableLocation(
            QStandardPaths.PicturesLocation) or ''
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Collage",
            pictures_dir,
            f"{fmt.upper()} (*.{fmt})",
            options=options,
        )
        if not path:
            return None
        return path if path.lower().endswith(f".{fmt}") else f"{path}.{fmt}"

    def _render_scaled_pixmap(self, resolution: int) -> QPixmap:
        """Render the collage at a scaled resolution with DPI awareness and clamping.

        - Multiplies logical size by ``resolution`` and device pixel ratio.
        - Clamps the largest side to ``config.MAX_EXPORT_DIMENSION`` to avoid excessive memory usage.
        """
        base = self.collage.size()
        dpr = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0
        scale = max(1.0, float(resolution) * float(dpr))
        out_w = int(base.width() * scale)
        out_h = int(base.height() * scale)
        # Clamp to max export dimension
        max_dim = max(out_w, out_h)
        if max_dim > config.MAX_EXPORT_DIMENSION:
            factor = config.MAX_EXPORT_DIMENSION / max_dim
            out_w = max(1, int(out_w * factor))
            out_h = max(1, int(out_h * factor))

        # Use QImage for deterministic pixel buffer
        img = QImage(out_w, out_h, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHints(QPainter.Antialiasing |
                         QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        # Render from logical coordinates scaled to pixel buffer size
        p.scale(out_w / base.width(), out_h / base.height())
        self.collage.render(p)
        p.end()
        return QPixmap.fromImage(img)

    def _add_images(self):
        # Select multiple images and fill empty cells in reading order
        exts = [f"*.{e}" for e in config.SUPPORTED_IMAGE_FORMATS]
        pattern = " ".join(exts)
        files, _ = QFileDialog.getOpenFileNames(self, "Add Images", QStandardPaths.writableLocation(
            QStandardPaths.PicturesLocation) or "", f"Images ({pattern})")
        if not files:
            return
        # Collect empty cells
        empty_cells = [
            c for c in self.collage.cells if not getattr(c, 'pixmap', None)]
        if not empty_cells:
            QMessageBox.information(
                self, "No Empty Cells", "All cells already contain images.")
            return
        assigned = 0
        for path, cell in zip(files, empty_cells):
            try:
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                img = reader.read()
                if img.isNull():
                    logging.warning("Skipping invalid image: %s", path)
                    continue
                # Optimize for current cell size
                optimized = ImageOptimizer.optimize_image(img, cell.size())
                display_pix = QPixmap.fromImage(optimized)
                original_pix = QPixmap.fromImage(img)
                cell.setImage(display_pix, original=original_pix)
                assigned += 1
            except Exception as e:
                logging.warning("Failed to add image %s: %s", path, e)
        if assigned < len(files):
            QMessageBox.information(
                self, "Some files skipped", f"Added {assigned} images; others could not be loaded or no empty cells left.")

    def _convert_for_jpeg(self, pix: QPixmap) -> QPixmap:
        img = pix.toImage()
        if img.hasAlphaChannel():
            rgb = img.convertToFormat(QImage.Format_RGB32)
            return QPixmap.fromImage(rgb)
        return pix

    def _save_original(self, path, fmt, quality):
        # Compute full-original grid size
        total_w = 0
        total_h = 0
        # widths and heights by column/row
        col_widths = [0]*self.collage.columns
        row_heights = [0]*self.collage.rows
        for cell in self.collage.cells:
            pos = self.collage.get_cell_position(cell)
            if cell.original_pixmap and pos:
                w = cell.original_pixmap.width()
                h = cell.original_pixmap.height()
                r, c = pos
                col_widths[c] = max(col_widths[c], w)
                row_heights[r] = max(row_heights[r], h)
        total_w = sum(col_widths)
        total_h = sum(row_heights)

        if total_w <= 0 or total_h <= 0:
            QMessageBox.information(
                self, "No Original Images", "There are no original images to export.")
            return

        canvas = QPixmap(total_w, total_h)
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        y_offset = 0
        for r in range(self.collage.rows):
            x_offset = 0
            for c in range(self.collage.columns):
                cell = self.collage.get_cell_at(r, c)
                if cell and cell.original_pixmap:
                    painter.drawPixmap(
                        QPoint(x_offset, y_offset), cell.original_pixmap)
                x_offset += col_widths[c]
            y_offset += row_heights[r]
        painter.end()

        if fmt in ['jpeg', 'jpg']:
            canvas = self._convert_for_jpeg(canvas)
        if not canvas.save(path, fmt, quality):
            raise IOError(f"Failed to save original collage to {path}")
        logging.info("Saved original collage to %s", path)

    def get_collage_state(self):
        # Serialize minimal state for autosave
        state = {
            'rows': self.collage.rows,
            'columns': self.collage.columns,
            # Further details omitted for brevity
        }
        return state


if __name__ == '__main__':
    app = QApplication(sys.argv)
    qss = Path(__file__).resolve().parents[1] / 'ui' / 'style.qss'
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding='utf-8'))
    # Apply design tokens on top of static QSS (allow env override for theme)
    theme = os.environ.get('COLLAGE_THEME', 'light')
    style_tokens.apply_tokens(app, theme=theme)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
