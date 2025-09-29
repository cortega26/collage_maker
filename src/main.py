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
    QDialog, QSlider, QDialogButtonBox, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt, QSize, QPoint, QStandardPaths
from PySide6.QtGui import QPainter, QPixmap, QKeySequence, QShortcut, QImage
from dataclasses import dataclass

from pathlib import Path
try:
    # Preferred package-relative imports
    from . import config
    from .widgets.collage import CollageWidget
    from .managers.autosave import AutosaveManager
    from .managers.performance import PerformanceMonitor
    from .managers.recovery import ErrorRecoveryManager
except ImportError:
    # Fallback for running `python src/main.py` directly
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import config
    from src.widgets.collage import CollageWidget
    from src.managers.autosave import AutosaveManager
    from src.managers.performance import PerformanceMonitor
    from src.managers.recovery import ErrorRecoveryManager

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

        # Controls and collage
        main_layout.addLayout(self._create_controls())
        self.collage = CollageWidget(
            rows=self.rows_spin.value(),
            columns=self.cols_spin.value(),
            cell_size=config.DEFAULT_CELL_SIZE
        )
        main_layout.addWidget(self.collage, alignment=Qt.AlignCenter)

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

    def _create_controls(self):
        layout = QHBoxLayout()
        # Grid controls
        self.rows_spin = QSpinBox(); self.rows_spin.setRange(1,10); self.rows_spin.setValue(config.DEFAULT_ROWS)
        self.cols_spin = QSpinBox(); self.cols_spin.setRange(1,10); self.cols_spin.setValue(config.DEFAULT_COLUMNS)
        update_btn = QPushButton("Update Grid"); update_btn.clicked.connect(self._update_grid)
        update_btn.setToolTip("Apply rows/cols to rebuild the grid")
        layout.addWidget(QLabel("Rows:")); layout.addWidget(self.rows_spin)
        layout.addWidget(QLabel("Cols:")); layout.addWidget(self.cols_spin)
        layout.addWidget(update_btn)

        # Save controls
        add_btn = QPushButton("Add Images…"); add_btn.clicked.connect(self._add_images); add_btn.setToolTip("Add images to empty cells")
        layout.addWidget(add_btn)
        clear_btn = QPushButton("Clear All"); clear_btn.clicked.connect(self._reset_collage); clear_btn.setToolTip("Clear all images and merges")
        layout.addWidget(clear_btn)
        save_btn = QPushButton("Save Collage"); save_btn.clicked.connect(self._show_save_dialog); save_btn.setToolTip("Export the collage to PNG/JPEG/WEBP")
        layout.addWidget(save_btn)

        return layout

    def _create_shortcuts(self):
        QShortcut(QKeySequence(config.SAVE_SHORTCUT), self, activated=self._show_save_dialog)
        QShortcut(QKeySequence(config.SAVE_ORIGINAL_SHORTCUT), self, activated=lambda: self._show_save_dialog(default_original=True))
        QShortcut(QKeySequence.Undo, self, activated=self._undo)
        QShortcut(QKeySequence.Redo, self, activated=self._redo)
        QShortcut(QKeySequence.SelectAll, self, activated=self._select_all)
        QShortcut(QKeySequence.Delete, self, activated=self._delete_selected)

    def _update_grid(self):
        self.collage.update_grid(self.rows_spin.value(), self.cols_spin.value())

    def _reset_collage(self):
        self.collage.clear()

    def _undo(self):
        # Unimplemented: placeholder for undo stack
        pass

    def _redo(self):
        pass

    def _select_all(self):
        for cell in self.collage.cells:
            cell.selected = True; cell.update()

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
            if opts.format in ('jpeg','jpg'):
                primary = self._convert_for_jpeg(primary)
            primary.save(path, opts.format, opts.quality)
            logging.info("Saved collage to %s", path)

            if opts.save_original:
                orig_path = os.path.splitext(path)[0] + '_original.' + opts.format
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
        pix = self.collage.grab().scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        preview.setPixmap(pix)
        v.addWidget(preview, alignment=Qt.AlignCenter)

        original = QCheckBox("Save Original at full resolution")
        original.setChecked(default_original)
        v.addWidget(original)

        fmt_box = QComboBox(); fmt_box.addItems(["PNG", "JPEG", "WEBP"])
        v.addWidget(fmt_box)

        v.addWidget(QLabel("Quality / Compression:"))
        quality = QSlider(Qt.Horizontal); quality.setRange(config.QUALITY_MIN, config.QUALITY_MAX); quality.setValue(config.QUALITY_DEFAULT)
        v.addWidget(quality)

        v.addWidget(QLabel("Resolution:"))
        res_box = QComboBox(); res_box.addItems([f"{m}x" for m in config.RESOLUTION_MULTIPLIERS])
        v.addWidget(res_box)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept); btns.rejected.connect(dialog.reject)
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
        pictures_dir = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or ''
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
        base_size = self.collage.size()
        out_size = QSize(base_size.width()*resolution, base_size.height()*resolution)
        primary = QPixmap(out_size); primary.fill(Qt.transparent)
        p = QPainter(primary)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        p.scale(resolution, resolution)
        self.collage.render(p); p.end()
        return primary

    def _add_images(self):
        # Select multiple images and fill empty cells in reading order
        exts = [f"*.{e}" for e in config.SUPPORTED_IMAGE_FORMATS]
        pattern = " ".join(exts)
        files, _ = QFileDialog.getOpenFileNames(self, "Add Images", QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or "", f"Images ({pattern})")
        if not files:
            return
        # Collect empty cells
        empty_cells = [c for c in self.collage.cells if not getattr(c, 'pixmap', None)]
        if not empty_cells:
            QMessageBox.information(self, "No Empty Cells", "All cells already contain images.")
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
                from .optimizer import ImageOptimizer
                optimized = ImageOptimizer.optimize_image(img, cell.size())
                cell.setImage(QPixmap.fromImage(optimized))
                assigned += 1
            except Exception as e:
                logging.warning("Failed to add image %s: %s", path, e)
        if assigned < len(files):
            QMessageBox.information(self, "Some files skipped", f"Added {assigned} images; others could not be loaded or no empty cells left.")

    def _convert_for_jpeg(self, pix: QPixmap) -> QPixmap:
        img = pix.toImage()
        if img.hasAlphaChannel():
            rgb = img.convertToFormat(QImage.Format_RGB32)
            return QPixmap.fromImage(rgb)
        return pix

    def _save_original(self, path, fmt, quality):
        # Compute full-original grid size
        total_w = 0; total_h = 0
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

        canvas = QPixmap(total_w, total_h); canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        y_offset = 0
        for r in range(self.collage.rows):
            x_offset = 0
            for c in range(self.collage.columns):
                cell = self.collage.get_cell_at(r, c)
                if cell and cell.original_pixmap:
                    painter.drawPixmap(QPoint(x_offset, y_offset), cell.original_pixmap)
                x_offset += col_widths[c]
            y_offset += row_heights[r]
        painter.end()

        if fmt in ['jpeg','jpg']:
            canvas = self._convert_for_jpeg(canvas)
        canvas.save(path, fmt, quality)
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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
