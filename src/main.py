# main.py
"""
Entry point and main application window for Collage Maker.
"""
import logging
import os
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from PySide6.QtCore import QPoint, QStandardPaths, Qt, QThreadPool, QTimer
from PySide6.QtGui import (
    QImage,
    QImageReader,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from utils.validation import validate_image_path, validate_output_path

try:
    # Preferred package-relative imports
    from . import config, style_tokens
    from .controllers import (
        CollageSessionController,
        CollageStateAdapter,
        RedoUnavailableError,
        UndoUnavailableError,
    )
    from .managers.autosave import AutosaveManager
    from .managers.performance import PerformanceMonitor
    from .managers.recovery import ErrorRecoveryManager
    from .optimizer import ImageOptimizer
    from .widgets.collage import CollageWidget
    from .widgets.control_panel import CaptionDefaults, ControlPanel, GridDefaults
    from .workers import Worker
except ImportError:
    # Fallback for running `python src/main.py` directly
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import config, style_tokens
    from src.controllers import (
        CollageSessionController,
        CollageStateAdapter,
        RedoUnavailableError,
        UndoUnavailableError,
    )
    from src.managers.autosave import AutosaveManager
    from src.managers.performance import PerformanceMonitor
    from src.managers.recovery import ErrorRecoveryManager
    from src.optimizer import ImageOptimizer
    from src.widgets.collage import CollageWidget
    from src.widgets.control_panel import CaptionDefaults, ControlPanel, GridDefaults
    from src.workers import Worker

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

        # Controls and collage
        self.control_panel = ControlPanel(
            grid_defaults=GridDefaults(
                rows=config.DEFAULT_ROWS,
                columns=config.DEFAULT_COLUMNS,
                templates=("2x2", "3x3", "2x3", "3x2", "4x4"),
            ),
            caption_defaults=CaptionDefaults(
                font_family="Impact",
                font_size=32,
                stroke_width=3,
                uppercase=True,
                show_top=True,
                show_bottom=True,
            ),
            parent=self,
        )
        main_layout.addWidget(self.control_panel)
        self._bind_control_panel()
        self.caption_timer = QTimer(self)
        self.caption_timer.setSingleShot(True)
        self.caption_timer.setInterval(150)
        self.caption_timer.timeout.connect(self._apply_captions_now)
        # Separator under the toolbar (thin)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)
        self.collage = CollageWidget(
            rows=self.rows_spin.value(),
            columns=self.cols_spin.value(),
            cell_size=config.DEFAULT_CELL_SIZE,
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
            self, save_state=self.get_collage_state, reset_callback=self._reset_collage
        )

        # Shortcuts
        self._create_shortcuts()

        # History tracking for undo / redo
        self._init_history_tracking()
        self._caption_snapshot_captured = False

        logging.info("MainWindow initialized.")

    def _bind_control_panel(self) -> None:
        panel = self.control_panel

        self.rows_spin = panel.rows_spin
        self.cols_spin = panel.cols_spin
        self.template_combo = panel.template_combo
        self.top_visible_chk = panel.top_checkbox
        self.bottom_visible_chk = panel.bottom_checkbox
        self.font_combo = panel.font_combo
        self.font_size_spin = panel.font_size_spin
        self.stroke_width_spin = panel.stroke_width_spin
        self.stroke_btn = panel.stroke_button
        self.fill_btn = panel.fill_button
        self.uppercase_chk = panel.uppercase_checkbox

        panel.addImagesRequested.connect(self._add_images)
        panel.mergeRequested.connect(self._merge_selected_cells)
        panel.splitRequested.connect(self._split_selected_cells)
        panel.clearRequested.connect(self._reset_collage)
        panel.saveRequested.connect(self._show_save_dialog)
        panel.updateGridRequested.connect(self._update_grid)
        panel.templateSelected.connect(self._apply_template)
        panel.captionSettingsChanged.connect(self._schedule_caption_apply)
        panel.fontSizeSpinChanged.connect(self._on_font_size_spin_changed)
        panel.colorPickRequested.connect(self._pick_color)

    def _schedule_caption_apply(self) -> None:
        if self.caption_timer.isActive():
            self.caption_timer.stop()
        self.caption_timer.start()

    def _pick_color(self, which: str):
        col = QColorDialog.getColor(parent=self)
        if not col.isValid():
            return
        self._ensure_caption_snapshot()
        changed = False
        for cell in [c for c in self.collage.cells if getattr(c, "selected", False)]:
            cell_changed = False
            if which == "stroke":
                if cell.caption_stroke_color != col:
                    cell.caption_stroke_color = col
                    cell_changed = True
            else:
                if cell.caption_fill_color != col:
                    cell.caption_fill_color = col
                    cell_changed = True
            if cell_changed:
                cell.update()
                changed = True
        self._finalize_caption_snapshot(changed=changed)

    def _apply_captions_now(self):
        if self.caption_timer.isActive():
            self.caption_timer.stop()
        self._ensure_caption_snapshot()
        show_top = self.top_visible_chk.isChecked()
        show_bottom = self.bottom_visible_chk.isChecked()
        family = self.font_combo.currentFont().family()
        font_sz = self.font_size_spin.value()
        stroke_w = self.stroke_width_spin.value()
        upper = self.uppercase_chk.isChecked()
        changed = False
        for cell in [c for c in self.collage.cells if getattr(c, "selected", False)]:
            cell_changed = False
            if cell.top_caption and cell.show_top_caption != show_top:
                cell.show_top_caption = show_top
                cell_changed = True
            if cell.bottom_caption and cell.show_bottom_caption != show_bottom:
                cell.show_bottom_caption = show_bottom
                cell_changed = True
            if cell.caption_font_family != family:
                cell.caption_font_family = family
                cell_changed = True
            if cell.caption_min_size != font_sz or cell.caption_max_size != font_sz:
                cell.caption_min_size = font_sz
                cell.caption_max_size = font_sz
                cell_changed = True
            if cell.caption_stroke_width != stroke_w:
                cell.caption_stroke_width = stroke_w
                cell_changed = True
            if cell.caption_uppercase != upper:
                cell.caption_uppercase = upper
                cell_changed = True
            if cell_changed:
                cell.update()
                changed = True
        self._finalize_caption_snapshot(changed=changed)

    def _on_font_size_spin_changed(self, value: int) -> None:
        self._schedule_caption_apply()

    def _set_font_size_controls(self, value: int) -> None:
        clamped = max(
            self.font_size_spin.minimum(),
            min(self.font_size_spin.maximum(), int(value)),
        )
        self.font_size_spin.blockSignals(True)
        self.font_size_spin.setValue(clamped)
        self.font_size_spin.blockSignals(False)

    def _create_shortcuts(self):
        QShortcut(
            QKeySequence(config.SAVE_SHORTCUT), self, activated=self._show_save_dialog
        )
        QShortcut(
            QKeySequence(config.SAVE_ORIGINAL_SHORTCUT),
            self,
            activated=lambda: self._show_save_dialog(default_original=True),
        )
        QShortcut(QKeySequence.Undo, self, activated=self._undo)
        QShortcut(QKeySequence.Redo, self, activated=self._redo)
        QShortcut(QKeySequence.SelectAll, self, activated=self._select_all)
        QShortcut(QKeySequence.Delete, self, activated=self._delete_selected)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._add_images)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self._reset_collage)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._merge_selected_cells)
        QShortcut(
            QKeySequence("Ctrl+Shift+M"), self, activated=self._split_selected_cells
        )

    # --- Undo / Redo helpers ---
    def _init_history_tracking(self) -> None:
        adapter = CollageStateAdapter(
            read_state=self.get_collage_state,
            apply_state=self._apply_state_from_snapshot,
        )
        self.session_controller = CollageSessionController(
            adapter,
            history_limit=30,
        )

    def _ensure_caption_snapshot(self) -> None:
        """Capture a snapshot for caption/style changes if needed."""

        if self._caption_snapshot_captured:
            return
        self._caption_snapshot_captured = self._capture_for_undo()

    def _finalize_caption_snapshot(self, *, changed: bool) -> None:
        """Finalize caption/style snapshot handling based on *changed*."""

        if not self._caption_snapshot_captured:
            return
        if changed:
            self._update_history_baseline()
        else:
            self._discard_latest_snapshot()
        self._caption_snapshot_captured = False

    def _capture_for_undo(self) -> bool:
        """Store the current baseline before a modifying action."""

        return self.session_controller.capture_snapshot()

    def _discard_latest_snapshot(self) -> None:
        self.session_controller.discard_latest_snapshot()

    def _update_history_baseline(self) -> None:
        self.session_controller.update_baseline()

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

    def _apply_state_from_snapshot(self, state: Dict[str, Any]) -> None:
        if not state:
            return

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
                if template in [
                    self.template_combo.itemText(i)
                    for i in range(self.template_combo.count())
                ]:
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
                font_value = captions.get(
                    "min_size",
                    captions.get("max_size", self.font_size_spin.value()),
                )
            self._set_font_size_controls(int(font_value))

            self.stroke_width_spin.blockSignals(True)
            self.stroke_width_spin.setValue(
                int(captions.get("stroke_width", self.stroke_width_spin.value()))
            )
            self.stroke_width_spin.blockSignals(False)

            self.uppercase_chk.blockSignals(True)
            self.uppercase_chk.setChecked(
                bool(captions.get("uppercase", self.uppercase_chk.isChecked()))
            )
            self.uppercase_chk.blockSignals(False)

        self.collage.update()

    def _restore_state(self, state: Dict[str, Any]) -> None:
        self.session_controller.restore_state(state)

    def _undo(self):
        try:
            self.session_controller.undo()
        except UndoUnavailableError:
            return

    def _redo(self):
        try:
            self.session_controller.redo()
        except RedoUnavailableError:
            return

    def _select_all(self):
        for cell in self.collage.cells:
            cell.selected = True
            cell.update()

    def _delete_selected(self):
        targets = [
            cell
            for cell in self.collage.cells
            if cell.selected
            and (
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
                "Select two or more adjacent cells to merge into a single region.",
            )
            return
        captured = self._capture_for_undo()
        if not self.collage.merge_cells(*rect):
            if captured:
                self._discard_latest_snapshot()
            QMessageBox.information(
                self, "Merge Cells", "Could not merge the selected cells."
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
                "Select a merged cell to split back into individual cells.",
            )
            return
        captured = self._capture_for_undo()
        if not self.collage.split_cells(*target_pos):
            if captured:
                self._discard_latest_snapshot()
            QMessageBox.information(
                self, "Split Cells", "Could not split the selected merged cell."
            )
            return
        if captured:
            self._update_history_baseline()

    def _show_save_dialog(self, default_original: bool = False):
        opts = self._prompt_save_options(default_original)
        if not opts:
            return
        self._export_collage(opts)

    def _export_collage(self, opts: "MainWindow.SaveOptions"):
        try:
            path = self._select_save_path(opts.format)
            if not path:
                return
            primary = self._render_scaled_image(opts.resolution)
            primary.setText("Software", "Collage Maker")
            fmt = opts.format.lower()
            if fmt in ("jpeg", "jpg"):
                primary = self._ensure_image_format(primary, fmt)

            original_payload: tuple[str | None, QImage | None]
            original_payload = (None, None)
            if opts.save_original:
                composed = self._compose_original_image()
                if composed is None:
                    QMessageBox.information(
                        self,
                        "No Original Images",
                        "There are no original images to export.",
                    )
                else:
                    if fmt in ("jpeg", "jpg"):
                        composed = self._ensure_image_format(composed, fmt)
                    orig_path = os.path.splitext(path)[0] + f"_original.{fmt}"
                    original_payload = (orig_path, composed)

            self._run_export_worker(path, fmt, opts.quality, primary, original_payload)
        except Exception as e:
            logging.error("Save failed: %s", e)
            QMessageBox.critical(self, "Error", f"Could not save collage: {e}")

    @dataclass(slots=True)
    class SaveOptions:
        format: str
        quality: int
        resolution: int
        save_original: bool

    def _prompt_save_options(
        self, default_original: bool = False
    ) -> "MainWindow.SaveOptions | None":
        dialog = QDialog(self)
        dialog.setWindowTitle("Save Collage")
        v = QVBoxLayout(dialog)

        preview = QLabel()
        pix = self.collage.grab().scaled(
            300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        preview.setPixmap(pix)
        v.addWidget(preview, alignment=Qt.AlignCenter)

        original = QCheckBox("Save Original at full resolution")
        original.setChecked(default_original)
        v.addWidget(original)

        fmt_box = QComboBox()
        fmt_box.addItem("PNG", userData="png")
        fmt_box.addItem("JPG", userData="jpg")
        fmt_box.addItem("JPEG", userData="jpeg")
        fmt_box.addItem("WEBP", userData="webp")
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

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        v.addWidget(btns)

        if dialog.exec() != QDialog.Accepted:
            return None
        return MainWindow.SaveOptions(
            format=str(fmt_box.currentData()),
            quality=quality.value(),
            resolution=int(res_box.currentText().rstrip("x")),
            save_original=original.isChecked(),
        )

    def _select_save_path(self, fmt: str) -> "str | None":
        options = QFileDialog.Options()
        if sys.platform.startswith("win"):
            options |= QFileDialog.DontUseNativeDialog
        pictures_dir = (
            QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or ""
        )
        fmt = fmt.lower()
        filter_patterns = {
            "png": "PNG (*.png)",
            "jpg": "JPG (*.jpg *.jpeg)",
            "jpeg": "JPEG (*.jpeg *.jpg)",
            "webp": "WEBP (*.webp)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Collage",
            pictures_dir,
            filter_patterns.get(fmt, f"{fmt.upper()} (*.{fmt})"),
            options=options,
        )
        if not path:
            return None
        input_path = Path(path)
        if not input_path.suffix:
            default_ext = {
                "jpeg": ".jpeg",
                "jpg": ".jpg",
            }.get(fmt, f".{fmt}")
            path_with_ext = f"{path}{default_ext}"
        else:
            path_with_ext = path

        allowed_exts = {f".{fmt}"}
        if fmt in {"jpeg", "jpg"}:
            allowed_exts.update({".jpg", ".jpeg"})

        try:
            validated = validate_output_path(path_with_ext, allowed_exts)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Invalid save location",
                f"Cannot save collage: {exc}",
            )
            return None

        return str(validated)

    def _run_export_worker(
        self,
        path: str,
        fmt: str,
        quality: int,
        primary: QImage,
        original_payload: tuple[str | None, QImage | None],
    ) -> None:
        dialog = QProgressDialog("Saving collage...", "", 0, 0, self)
        dialog.setWindowTitle("Saving")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setCancelButton(None)
        dialog.setMinimumDuration(0)
        dialog.show()

        orig_path, orig_image = original_payload

        def _write_files() -> tuple[str, str | None]:
            uppercase_fmt = "JPEG" if fmt in {"jpeg", "jpg"} else fmt.upper()
            if not primary.save(path, uppercase_fmt, quality):
                raise IOError(f"Failed to save collage to {path}")
            if orig_path and orig_image is not None:
                if not orig_image.save(orig_path, uppercase_fmt, quality):
                    raise IOError(f"Failed to save original collage to {orig_path}")
            return path, orig_path

        worker = Worker(_write_files)

        def _on_result(result: tuple[str, str | None]) -> None:
            saved_path, original_path = result
            message = f"Saved: {saved_path}"
            if original_path:
                message = f"{message}\nOriginal: {original_path}"
            logging.info("Saved collage to %s", saved_path)
            if original_path:
                logging.info("Saved original collage to %s", original_path)
            QMessageBox.information(self, "Saved", message)

        def _on_error(message: str) -> None:
            logging.error("Save failed: %s", message)
            QMessageBox.critical(self, "Error", f"Could not save collage: {message}")

        def _on_finished() -> None:
            dialog.close()

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)

        QThreadPool.globalInstance().start(worker)

    def _render_scaled_image(self, resolution: int) -> QImage:
        """Render the collage at a scaled resolution with DPI awareness and clamping.

        - Multiplies logical size by ``resolution`` and device pixel ratio.
        - Clamps the largest side to ``config.MAX_EXPORT_DIMENSION`` to avoid excessive memory usage.
        """
        base = self.collage.size()
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
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
        p.setRenderHints(
            QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
            | QPainter.TextAntialiasing
        )
        # Render from logical coordinates scaled to pixel buffer size
        p.scale(out_w / base.width(), out_h / base.height())
        self.collage.render(p)
        p.end()
        return img

    def _validate_selected_images(
        self, selections: Sequence[str]
    ) -> tuple[list[Path], list[str]]:
        """Validate user-selected image paths.

        Returns a tuple containing validated ``Path`` objects and human-readable
        error messages for any rejected selections.
        """

        allowed_exts = {
            f".{ext.lower().lstrip('.')}" for ext in config.SUPPORTED_IMAGE_FORMATS
        }
        valid_paths: list[Path] = []
        errors: list[str] = []
        for selection in selections:
            try:
                validated = validate_image_path(selection, allowed_exts)
            except ValueError as exc:
                errors.append(f"{selection}: {exc}")
                logging.warning(
                    "Skipping invalid image selection %s: %s", selection, exc
                )
                continue
            valid_paths.append(validated)
        return valid_paths, errors

    def _add_images(self):
        # Select multiple images and fill empty cells in reading order
        exts = [f"*.{e}" for e in config.SUPPORTED_IMAGE_FORMATS]
        pattern = " ".join(exts)
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Images",
            QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or "",
            f"Images ({pattern})",
        )
        if not files:
            return
        # Collect empty cells
        empty_cells = [c for c in self.collage.cells if not getattr(c, "pixmap", None)]
        if not empty_cells:
            QMessageBox.information(
                self, "No Empty Cells", "All cells already contain images."
            )
            return
        valid_paths, validation_errors = self._validate_selected_images(files)
        if not valid_paths:
            details = "\n".join(validation_errors[:3])
            if len(validation_errors) > 3:
                details += f"\n…{len(validation_errors) - 3} more rejected selections."
            QMessageBox.warning(
                self,
                "No Valid Images",
                "None of the selected files could be added:\n" + details,
            )
            return

        captured = self._capture_for_undo()
        assigned = 0
        attempted = min(len(valid_paths), len(empty_cells))
        for path, cell in zip(valid_paths, empty_cells):
            try:
                reader = QImageReader(str(path))
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
        issues: list[str] = []
        if assigned < attempted:
            issues.append(
                f"{attempted - assigned} file(s) could not be decoded and were skipped."
            )
        remaining_capacity = len(valid_paths) - attempted
        if remaining_capacity > 0:
            issues.append(
                f"Only {len(empty_cells)} empty cell(s) were available; {remaining_capacity}"
                " selection(s) were not placed."
            )
        if validation_errors:
            details = "\n".join(validation_errors[:3])
            if len(validation_errors) > 3:
                details += f"\n…{len(validation_errors) - 3} more rejected selections."
            issues.append("Validation rejected the following selections:\n" + details)
        if issues:
            QMessageBox.information(
                self,
                "Some files skipped",
                "\n\n".join(issues),
            )

    def _ensure_image_format(self, image: QImage, fmt: str) -> QImage:
        if fmt in ("jpeg", "jpg") and image.hasAlphaChannel():
            return image.convertToFormat(QImage.Format_RGB32)
        return image

    def _compose_original_image(self) -> QImage | None:
        # Compute full-original grid size
        total_w = 0
        total_h = 0
        # widths and heights by column/row
        col_widths = [0] * self.collage.columns
        row_heights = [0] * self.collage.rows
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
            return None

        canvas = QImage(total_w, total_h, QImage.Format_ARGB32)
        canvas.fill(Qt.transparent)
        painter = QPainter()
        painter.begin(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        y_offset = 0
        for r in range(self.collage.rows):
            x_offset = 0
            for c in range(self.collage.columns):
                cell = self.collage.get_cell_at(r, c)
                if cell and cell.original_pixmap:
                    painter.drawImage(
                        QPoint(x_offset, y_offset), cell.original_pixmap.toImage()
                    )
                x_offset += col_widths[c]
            y_offset += row_heights[r]
        painter.end()
        return canvas

    def get_collage_state(self):
        """Return a richer snapshot for autosave and recovery."""
        collage_state = self.collage.serialize_for_autosave()
        controls_state = {
            "rows": self.rows_spin.value(),
            "columns": self.cols_spin.value(),
            "template": (
                self.template_combo.currentText()
                if hasattr(self, "template_combo")
                else None
            ),
        }
        captions_state = {
            "show_top": self.top_visible_chk.isChecked(),
            "show_bottom": self.bottom_visible_chk.isChecked(),
            "font_family": self.font_combo.currentText(),
            "font_size": self.font_size_spin.value(),
            "min_size": self.font_size_spin.value(),
            "max_size": self.font_size_spin.value(),
            "stroke_width": self.stroke_width_spin.value(),
            "uppercase": self.uppercase_chk.isChecked(),
        }
        return {
            "collage": collage_state,
            "controls": controls_state,
            "captions": captions_state,
        }


if __name__ == "__main__":
    app = QApplication(sys.argv)
    qss = Path(__file__).resolve().parents[1] / "ui" / "style.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))
    # Apply design tokens on top of static QSS (allow env override for theme)
    theme = os.environ.get("COLLAGE_THEME", "light")
    style_tokens.apply_tokens(app, theme=theme)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
