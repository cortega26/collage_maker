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
from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtGui import QPainter, QPixmap, QKeySequence, QShortcut, QImage

import config
from cache import image_cache
from optimizer import ImageOptimizer
from widgets.collage import CollageWidget
from workers import TaskQueue, Worker
from managers.autosave import AutosaveManager
from managers.performance import PerformanceMonitor
from managers.recovery import ErrorRecoveryManager

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
        layout.addWidget(QLabel("Rows:")); layout.addWidget(self.rows_spin)
        layout.addWidget(QLabel("Cols:")); layout.addWidget(self.cols_spin)
        layout.addWidget(update_btn)

        # Save controls
        save_btn = QPushButton("Save Collage"); save_btn.clicked.connect(self._show_save_dialog)
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
        dialog = QDialog(self)
        dialog.setWindowTitle("Save Collage")
        dlg_layout = QVBoxLayout(dialog)

        # Preview
        preview = QLabel()
        pix = self.collage.grab().scaled(300,300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        preview.setPixmap(pix)
        dlg_layout.addWidget(preview, alignment=Qt.AlignCenter)

        # Original export option
        self.original_checkbox = QCheckBox("Save Original at full resolution")
        self.original_checkbox.setChecked(default_original)
        dlg_layout.addWidget(self.original_checkbox)

        # Format combo
        self.format_combo = QComboBox(); self.format_combo.addItems(["PNG","JPEG","WebP"])
        dlg_layout.addWidget(self.format_combo)

        # Quality slider
        self.quality_slider = QSlider(Qt.Horizontal); self.quality_slider.setRange(config.QUALITY_MIN, config.QUALITY_MAX); self.quality_slider.setValue(config.QUALITY_DEFAULT)
        dlg_layout.addWidget(QLabel("Quality:")); dlg_layout.addWidget(self.quality_slider)

        # Resolution multiplier
        self.res_combo = QComboBox(); self.res_combo.addItems([f"{m}x" for m in config.RESOLUTION_MULTIPLIERS])
        dlg_layout.addWidget(QLabel("Resolution:")); dlg_layout.addWidget(self.res_combo)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept); btns.rejected.connect(dialog.reject)
        dlg_layout.addWidget(btns)

        if dialog.exec() == QDialog.Accepted:
            options = {
                'format': self.format_combo.currentText().lower(),
                'quality': self.quality_slider.value(),
                'resolution': int(self.res_combo.currentText().rstrip('x')),
                'save_original': self.original_checkbox.isChecked()
            }
            self._save_collage(options)

    def _save_collage(self, opts):
        try:
            # Primary export
            base_size = self.collage.size()
            out_size = QSize(base_size.width()*opts['resolution'], base_size.height()*opts['resolution'])
            primary = QPixmap(out_size); primary.fill(Qt.transparent)
            p = QPainter(primary)
            p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
            p.scale(opts['resolution'], opts['resolution'])
            self.collage.render(p); p.end()

            # Get filename
            path, _ = QFileDialog.getSaveFileName(self, "Save Collage", '', f"{opts['format'].upper()} (*.{opts['format']})")
            if not path:
                return
            if not path.lower().endswith(f".{opts['format']}"):
                path += f".{opts['format']}"

            # Save primary
            if opts['format'] in ['jpeg','jpg']:
                primary = self._convert_for_jpeg(primary)
            primary.save(path, opts['format'], opts['quality'])
            logging.info("Saved collage to %s", path)

            # Optional original export
            if opts['save_original']:
                orig_path = os.path.splitext(path)[0] + '_original.' + opts['format']
                self._save_original(orig_path, opts['format'], opts['quality'])

            QMessageBox.information(self, "Saved", f"Saved: {path}")

        except Exception as e:
            logging.error("Save failed: %s", e)
            QMessageBox.critical(self, "Error", f"Could not save collage: {e}")

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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
