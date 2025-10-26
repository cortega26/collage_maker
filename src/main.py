# main.py
"""
Entry point and main application window for Collage Maker.
"""
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
import copy
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSpinBox, QFileDialog, QMessageBox,
    QDialog, QSlider, QDialogButtonBox, QCheckBox, QComboBox,
    QFrame, QSizePolicy, QFontComboBox, QColorDialog
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

LOGGER_NAME = "collage_maker"


def configure_logging() -> logging.Logger:
    """Configure and return the application logger.

    The handler setup is idempotent to avoid duplicate handlers when the module
    is imported multiple times (e.g., in tests). A rotating file handler limits
    on-disk log growth while mirroring output to stdout for developer visibility.
    """

    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    log_path = Path(__file__).resolve().parents[1] / "collage_maker.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_048_576,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False

    return logger


logger = configure_logging()


def global_exception_handler(exc_type, value, tb):
    logger.error("Uncaught exception", exc_info=(exc_type, value, tb))
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
        control_panel = self._create_control_panel()
        main_layout.addWidget(control_panel)
        # Separator under the toolbar (thin)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)
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

        # History tracking for undo / redo
        self._init_history_tracking()

        logging.info("MainWindow initialized.")

    def _create_control_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("controlPanel")
        panel.setProperty("compact", "true")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        main_layout = QVBoxLayout(panel)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)

        control_height = 30

        spin_ss = f"""
        QSpinBox {{
            background-color: {self._colors.surface};
            color: {self._colors.text};
            border: 1px solid {self._colors.border};
            border-radius: 6px;
            padding: 1px 10px 1px 8px;\n            min-height: {control_height}px;
        }}
        QSpinBox QLineEdit {{
            background: transparent;
            color: {self._colors.text};
            selection-background-color: {self._colors.focus};
            selection-color: #ffffff;
            padding: 0px;
        }}
        QSpinBox:disabled {{ color: {self._colors.text_muted}; }}
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            background: {self._colors.surface};
            border-left: 1px solid {self._colors.border};
            width: 18px;
            margin: 1px 0px;
        }}
        QSpinBox::up-arrow {{
            width: 0; height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-bottom: 8px solid {self._colors.focus};
        }}
        QSpinBox::down-arrow {{
            width: 0; height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 8px solid {self._colors.focus};
        }}
        QSpinBox::up-arrow:disabled {{ border-bottom-color: {self._colors.text_muted}; }}
        QSpinBox::down-arrow:disabled {{ border-top-color: {self._colors.text_muted}; }}
        """

        combo_ss = f"""
        QComboBox {{
            background-color: {self._colors.surface};
            color: {self._colors.text};
            border: 1px solid {self._colors.border};
            border-radius: 6px;
            padding: 1px 22px 1px 8px;
            min-height: {control_height}px;
        }}
        QComboBox::drop-down {{
            width: 22px;
            border-left: 1px solid {self._colors.border};
            margin: 1px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {self._colors.surface};
            color: {self._colors.text};
            border: 1px solid {self._colors.border};
        }}
        """

        # -- Grid controls
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 10)
        self.rows_spin.setValue(config.DEFAULT_ROWS)
        self.rows_spin.setStyleSheet(spin_ss)
        self.rows_spin.setFixedHeight(control_height)
        self.rows_spin.setMaximumWidth(90)

        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 10)
        self.cols_spin.setValue(config.DEFAULT_COLUMNS)
        self.cols_spin.setStyleSheet(spin_ss)
        self.cols_spin.setFixedHeight(control_height)
        self.cols_spin.setMaximumWidth(90)

        self.template_combo = QComboBox()
        self.template_combo.addItems(["2x2", "3x3", "2x3", "3x2", "4x4"])
        self.template_combo.setAccessibleName("Templates")
        self.template_combo.currentTextChanged.connect(self._apply_template)
        self.template_combo.setFixedHeight(control_height)
        self.template_combo.setMinimumWidth(140)
        self.template_combo.setStyleSheet(combo_ss)

        update_btn = QPushButton("Update Grid")
        update_btn.clicked.connect(self._update_grid)

        grid_row = QGridLayout()
        grid_row.setVerticalSpacing(6)
        grid_row.setHorizontalSpacing(12)
        grid_row.addWidget(QLabel("Rows:"), 0, 0)
        grid_row.addWidget(self.rows_spin, 0, 1)
        grid_row.addWidget(QLabel("Cols:"), 0, 2)
        grid_row.addWidget(self.cols_spin, 0, 3)
        grid_row.addWidget(QLabel("Template:"), 0, 4)
        grid_row.addWidget(self.template_combo, 0, 5)
        grid_row.addWidget(update_btn, 0, 6)
        grid_row.setColumnStretch(5, 1)
        grid_row.setColumnStretch(6, 0)
        main_layout.addLayout(grid_row)

        # -- Primary actions
        actions = QHBoxLayout()
        actions.setSpacing(8)
        action_specs = [
            ("Add Images…", self._add_images),
            ("Merge", self._merge_selected_cells),
            ("Split", self._split_selected_cells),
            ("Clear All", self._reset_collage),
            ("Save Collage", self._show_save_dialog),
        ]
        for text, handler in action_specs:
            btn = QPushButton(text)
            btn.setFixedHeight(control_height)
            btn.clicked.connect(handler)
            actions.addWidget(btn)
        actions.addStretch(1)
        main_layout.addLayout(actions)

        # -- Caption controls
        self.top_visible_chk = QCheckBox("Show Top")
        self.top_visible_chk.setChecked(True)
        self.bottom_visible_chk = QCheckBox("Show Bottom")
        self.bottom_visible_chk.setChecked(True)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentText("Impact")
        self.font_combo.setFixedHeight(control_height)
        self.font_combo.setMinimumWidth(160)
        self.font_combo.setStyleSheet(combo_ss)

        size_label = QLabel("Font Size:")
        size_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.font_size_slider = QSlider(Qt.Horizontal)
        self.font_size_slider.setRange(8, 120)
        self.font_size_slider.setValue(32)
        self.font_size_slider.setFixedHeight(18)
        self.font_size_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 120)
        self.font_size_spin.setValue(self.font_size_slider.value())
        self.font_size_spin.setFixedHeight(control_height)
        self.font_size_spin.setMaximumWidth(80)
        self.font_size_spin.setStyleSheet(spin_ss)
        size_unit = QLabel("px")
        size_unit.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.stroke_width_spin = QSpinBox()
        self.stroke_width_spin.setRange(0, 16)
        self.stroke_width_spin.setValue(3)
        self.stroke_width_spin.setFixedHeight(control_height)
        self.stroke_width_spin.setMaximumWidth(80)
        self.stroke_width_spin.setStyleSheet(spin_ss)

        self.stroke_btn = QPushButton("Stroke Color")
        self.fill_btn = QPushButton("Fill Color")
        for btn in (self.stroke_btn, self.fill_btn):
            btn.setFixedHeight(control_height)

        self.uppercase_chk = QCheckBox("UPPERCASE")
        self.uppercase_chk.setChecked(True)

        caption_layout = QGridLayout()
        caption_layout.setHorizontalSpacing(10)
        caption_layout.setVerticalSpacing(6)
        caption_layout.addWidget(self.top_visible_chk, 0, 0)
        caption_layout.addWidget(self.bottom_visible_chk, 0, 1)
        caption_layout.addWidget(QLabel("Font:"), 0, 2)
        caption_layout.addWidget(self.font_combo, 0, 3)
        caption_layout.addWidget(size_label, 0, 4)
        caption_layout.addWidget(self.font_size_slider, 0, 5, 1, 3)
        caption_layout.addWidget(self.font_size_spin, 0, 8)
        caption_layout.addWidget(size_unit, 0, 9)
        caption_layout.addWidget(QLabel("Stroke:"), 1, 0)
        caption_layout.addWidget(self.stroke_width_spin, 1, 1)
        caption_layout.addWidget(self.stroke_btn, 1, 2)
        caption_layout.addWidget(self.fill_btn, 1, 3)
        caption_layout.addWidget(self.uppercase_chk, 1, 4)
        caption_layout.setColumnStretch(3, 1)
        caption_layout.setColumnStretch(5, 3)
        caption_layout.setColumnStretch(9, 1)
        main_layout.addLayout(caption_layout)

        self.font_size_slider.valueChanged.connect(self._on_font_size_slider_changed)
        self.font_size_spin.valueChanged.connect(self._on_font_size_spin_changed)

        from PySide6.QtCore import QTimer
        self.caption_timer = QTimer(self)
        self.caption_timer.setSingleShot(True)
        self.caption_timer.setInterval(150)
        self.caption_timer.timeout.connect(self._apply_captions_now)

        self.top_visible_chk.toggled.connect(lambda _: self._apply_captions_now())
        self.bottom_visible_chk.toggled.connect(lambda _: self._apply_captions_now())
        self.font_combo.currentFontChanged.connect(lambda _: self._apply_captions_now())
        self.stroke_width_spin.valueChanged.connect(lambda _: self._apply_captions_now())
        self.uppercase_chk.toggled.connect(lambda _: self._apply_captions_now())
        self.stroke_btn.clicked.connect(lambda: self._pick_color('stroke'))
        self.fill_btn.clicked.connect(lambda: self._pick_color('fill'))

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
        show_top = self.top_visible_chk.isChecked()
        show_bottom = self.bottom_visible_chk.isChecked()
        family = self.font_combo.currentFont().family()
        font_sz = self.font_size_spin.value()
        stroke_w = self.stroke_width_spin.value()
        upper = self.uppercase_chk.isChecked()
        for cell in [c for c in self.collage.cells if getattr(c, 'selected', False)]:
            if cell.top_caption:
                cell.show_top_caption = show_top
            if cell.bottom_caption:
                cell.show_bottom_caption = show_bottom
            cell.caption_font_family = family
            cell.caption_min_size = font_sz
            cell.caption_max_size = font_sz
            cell.caption_stroke_width = stroke_w
            cell.caption_uppercase = upper
            cell.update()

    def _on_font_size_slider_changed(self, value: int) -> None:
        if self.font_size_spin.value() != value:
            self.font_size_spin.blockSignals(True)
            self.font_size_spin.setValue(value)
            self.font_size_spin.blockSignals(False)
        self._apply_captions_now()

    def _on_font_size_spin_changed(self, value: int) -> None:
        if self.font_size_slider.value() != value:
            self.font_size_slider.blockSignals(True)
            self.font_size_slider.setValue(value)
            self.font_size_slider.blockSignals(False)
        self._apply_captions_now()

    def _set_font_size_controls(self, value: int) -> None:
        clamped = max(self.font_size_spin.minimum(), min(self.font_size_spin.maximum(), int(value)))
        self.font_size_spin.blockSignals(True)
        self.font_size_spin.setValue(clamped)
        self.font_size_spin.blockSignals(False)
        self.font_size_slider.blockSignals(True)
        self.font_size_slider.setValue(clamped)
        self.font_size_slider.blockSignals(False)


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
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._merge_selected_cells)
        QShortcut(QKeySequence("Ctrl+Shift+M"), self, activated=self._split_selected_cells)

    # --- Undo / Redo helpers ---
    def _init_history_tracking(self) -> None:
        self._history_limit = 30
        self._undo_stack: List[Dict[str, Any]] = []
        self._redo_stack: List[Dict[str, Any]] = []
        self._is_restoring_state = False
        self._history_baseline: Dict[str, Any] = copy.deepcopy(self.get_collage_state())

    def _capture_for_undo(self) -> bool:
        """Store the current baseline before a modifying action."""
        if self._is_restoring_state:
            return False
        snapshot = copy.deepcopy(self._history_baseline)
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        return True

    def _discard_latest_snapshot(self) -> None:
        if self._undo_stack:
            self._undo_stack.pop()

    def _update_history_baseline(self) -> None:
        self._history_baseline = copy.deepcopy(self.get_collage_state())

    def _update_grid(self):
        rows = self.rows_spin.value()
        cols = self.cols_spin.value()
        if rows == self.collage.rows and cols == self.collage.columns:
            return
        captured = self._capture_for_undo()
        try:
            self.collage.update_grid(rows, cols)
        except Exception as exc:
            if captured:
                self._discard_latest_snapshot()
            raise exc
        else:
            if captured:
                self._update_history_baseline()

    def _apply_template(self, name: str):
        try:
            r, c = name.split("x")
            self.rows_spin.setValue(int(r))
            self.cols_spin.setValue(int(c))
            self._update_grid()
        except Exception:
            pass

    def _reset_collage(self):
        has_content = any(
            getattr(cell, "pixmap", None) or getattr(cell, "caption", "")
            for cell in self.collage.cells
        ) or bool(getattr(self.collage, "merged_cells", {}))
        if not has_content:
            return
        captured = self._capture_for_undo()
        self.collage.clear()
        if captured:
            self._update_history_baseline()

    def _restore_state(self, state: Dict[str, Any]) -> None:
        if not state:
            return
        self._is_restoring_state = True
        try:
            controls = state.get("controls", {})
            captions = state.get("captions", {})
            collage_state = state.get("collage", {})

            if collage_state:
                self.collage.restore_from_serialized(collage_state)

            if controls:
                rows = controls.get("rows", self.rows_spin.value())
                cols = controls.get("columns", self.cols_spin.value())
                template = controls.get("template")

                self.rows_spin.blockSignals(True)
                self.rows_spin.setValue(rows)
                self.rows_spin.blockSignals(False)

                self.cols_spin.blockSignals(True)
                self.cols_spin.setValue(cols)
                self.cols_spin.blockSignals(False)

                if template and self.template_combo is not None:
                    if template in [self.template_combo.itemText(i) for i in range(self.template_combo.count())]:
                        self.template_combo.blockSignals(True)
                        self.template_combo.setCurrentText(template)
                        self.template_combo.blockSignals(False)

            if captions:
                self.top_visible_chk.blockSignals(True)
                self.top_visible_chk.setChecked(bool(captions.get("show_top", True)))
                self.top_visible_chk.blockSignals(False)

                self.bottom_visible_chk.blockSignals(True)
                self.bottom_visible_chk.setChecked(bool(captions.get("show_bottom", True)))
                self.bottom_visible_chk.blockSignals(False)

                font_family = captions.get("font_family")
                if font_family:
                    self.font_combo.blockSignals(True)
                    self.font_combo.setCurrentText(font_family)
                    self.font_combo.blockSignals(False)

                font_value = captions.get("font_size")
                if font_value is None:
                    font_value = captions.get("min_size", captions.get("max_size", self.font_size_spin.value()))
                self._set_font_size_controls(int(font_value))

                self.stroke_width_spin.blockSignals(True)
                self.stroke_width_spin.setValue(int(captions.get("stroke_width", self.stroke_width_spin.value())))
                self.stroke_width_spin.blockSignals(False)

                self.uppercase_chk.blockSignals(True)
                self.uppercase_chk.setChecked(bool(captions.get("uppercase", self.uppercase_chk.isChecked())))
                self.uppercase_chk.blockSignals(False)
        finally:
            self._is_restoring_state = False
        self._update_history_baseline()
        self.collage.update()

    def _undo(self):
        if not self._undo_stack:
            return
        snapshot = self._undo_stack.pop()
        current = copy.deepcopy(self.get_collage_state())
        self._redo_stack.append(current)
        if len(self._redo_stack) > self._history_limit:
            self._redo_stack.pop(0)
        self._restore_state(snapshot)

    def _redo(self):
        if not self._redo_stack:
            return
        snapshot = self._redo_stack.pop()
        current = copy.deepcopy(self.get_collage_state())
        self._undo_stack.append(current)
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self._restore_state(snapshot)

    def _select_all(self):
        for cell in self.collage.cells:
            cell.selected = True
            cell.update()

    def _delete_selected(self):
        targets = [
            cell for cell in self.collage.cells
            if cell.selected and (
                getattr(cell, "pixmap", None)
                or getattr(cell, "caption", "")
                or getattr(cell, "top_caption", "")
                or getattr(cell, "bottom_caption", "")
            )
        ]
        if not targets:
            return
        captured = self._capture_for_undo()
        for cell in targets:
            cell.clearImage()
        if captured:
            self._update_history_baseline()

    def _merge_selected_cells(self):
        rect = self.collage.selected_rectangle()
        if not rect:
            QMessageBox.information(
                self,
                "Merge Cells",
                "Select two or more adjacent cells to merge into a single region."
            )
            return
        captured = self._capture_for_undo()
        if not self.collage.merge_cells(*rect):
            if captured:
                self._discard_latest_snapshot()
            QMessageBox.information(
                self,
                "Merge Cells",
                "Could not merge the selected cells."
            )
            return
        target = self.collage.get_cell_at(rect[0], rect[1])
        if target:
            target.selected = True
        if captured:
            self._update_history_baseline()

    def _split_selected_cells(self):
        target_pos: Optional[tuple[int, int]] = None
        for cell in self.collage.cells:
            if not getattr(cell, "selected", False):
                continue
            if getattr(cell, "row_span", 1) == 1 and getattr(cell, "col_span", 1) == 1:
                continue
            position = self.collage.get_cell_position(cell)
            if position:
                target_pos = position
                break
        if not target_pos:
            QMessageBox.information(
                self,
                "Split Cells",
                "Select a merged cell to split back into individual cells."
            )
            return
        captured = self._capture_for_undo()
        if not self.collage.split_cells(*target_pos):
            if captured:
                self._discard_latest_snapshot()
            QMessageBox.information(
                self,
                "Split Cells",
                "Could not split the selected merged cell."
            )
            return
        if captured:
            self._update_history_baseline()

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
        captured = self._capture_for_undo()
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
        if assigned == 0 and captured:
            self._discard_latest_snapshot()
        elif captured and assigned > 0:
            self._update_history_baseline()
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
        """Return a richer snapshot for autosave and recovery."""
        collage_state = self.collage.serialize_for_autosave()
        controls_state = {
            'rows': self.rows_spin.value(),
            'columns': self.cols_spin.value(),
            'template': self.template_combo.currentText() if hasattr(self, 'template_combo') else None,
        }
        captions_state = {
            'show_top': self.top_visible_chk.isChecked(),
            'show_bottom': self.bottom_visible_chk.isChecked(),
            'font_family': self.font_combo.currentText(),
            'font_size': self.font_size_spin.value(),
            'min_size': self.font_size_spin.value(),
            'max_size': self.font_size_spin.value(),
            'stroke_width': self.stroke_width_spin.value(),
            'uppercase': self.uppercase_chk.isChecked(),
        }
        return {
            'collage': collage_state,
            'controls': controls_state,
            'captions': captions_state,
        }


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
