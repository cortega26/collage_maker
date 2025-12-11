"""
CollagePresenter: Handles application logic and state management, decoupled from MainWindow.
"""
import logging
from typing import Any, Dict, Optional

from PySide6.QtWidgets import QMessageBox

class CollagePresenter:
    def __init__(self, view):
        self.view = view
        self.logger = logging.getLogger("collage_maker.presenter")

    @property
    def collage(self):
        return self.view.collage

    def get_collage_state(self) -> Dict[str, Any]:
        """Return a richer snapshot for autosave and recovery."""
        collage_state = self.collage.serialize_for_autosave()
        
        # Access controls via view properties
        # Assuming view has exposed these or we access them directly
        # For this refactor, we assume 'view' is the MainWindow instance
        
        controls_state = {
            "rows": self.view.rows_spin.value(),
            "columns": self.view.cols_spin.value(),
            "template": (
                self.view.template_combo.currentText()
                if hasattr(self.view, "template_combo")
                else None
            ),
        }
        captions_state = {
            "show_top": self.view.top_visible_chk.isChecked(),
            "show_bottom": self.view.bottom_visible_chk.isChecked(),
            "font_family": self.view.font_combo.currentText(),
            "font_size": self.view.font_size_spin.value(),
            "min_size": self.view.font_size_spin.value(),
            "max_size": self.view.font_size_spin.value(),
            "stroke_width": self.view.stroke_width_spin.value(),
            "uppercase": self.view.uppercase_chk.isChecked(),
        }
        return {
            "collage": collage_state,
            "controls": controls_state,
            "captions": captions_state,
        }

    def apply_state(self, state: Dict[str, Any]) -> None:
        if not state:
            return

        controls = state.get("controls", {})
        captions = state.get("captions", {})
        collage_state = state.get("collage", {})

        if collage_state:
            self.collage.restore_from_serialized(collage_state)

        if controls:
            self._apply_controls_state(controls)

        if captions:
            self._apply_captions_state(captions)

        self.collage.update()

    def _apply_controls_state(self, controls: Dict[str, Any]) -> None:
        rows = controls.get("rows", self.view.rows_spin.value())
        cols = controls.get("columns", self.view.cols_spin.value())
        template = controls.get("template")

        self.view.rows_spin.blockSignals(True)
        self.view.rows_spin.setValue(rows)
        self.view.rows_spin.blockSignals(False)

        self.view.cols_spin.blockSignals(True)
        self.view.cols_spin.setValue(cols)
        self.view.cols_spin.blockSignals(False)

        if template and self.view.template_combo is not None:
            combo = self.view.template_combo
            if template in [combo.itemText(i) for i in range(combo.count())]:
                combo.blockSignals(True)
                combo.setCurrentText(template)
                combo.blockSignals(False)

    def _apply_captions_state(self, captions: Dict[str, Any]) -> None:
        self.view.top_visible_chk.blockSignals(True)
        self.view.top_visible_chk.setChecked(bool(captions.get("show_top", True)))
        self.view.top_visible_chk.blockSignals(False)

        self.view.bottom_visible_chk.blockSignals(True)
        self.view.bottom_visible_chk.setChecked(bool(captions.get("show_bottom", True)))
        self.view.bottom_visible_chk.blockSignals(False)

        font_family = captions.get("font_family")
        if font_family:
            self.view.font_combo.blockSignals(True)
            self.view.font_combo.setCurrentText(font_family)
            self.view.font_combo.blockSignals(False)

        font_value = captions.get("font_size")
        if font_value is None:
            font_value = captions.get(
                "min_size",
                captions.get("max_size", self.view.font_size_spin.value()),
            )
        # Helper on view
        if hasattr(self.view, "_set_font_size_controls"):
            self.view._set_font_size_controls(int(font_value))

        self.view.stroke_width_spin.blockSignals(True)
        self.view.stroke_width_spin.setValue(
            int(captions.get("stroke_width", self.view.stroke_width_spin.value()))
        )
        self.view.stroke_width_spin.blockSignals(False)

        self.view.uppercase_chk.blockSignals(True)
        self.view.uppercase_chk.setChecked(
            bool(captions.get("uppercase", self.view.uppercase_chk.isChecked()))
        )
        self.view.uppercase_chk.blockSignals(False)

    def reset_collage(self):
        has_content = any(
            getattr(cell, "pixmap", None) or getattr(cell, "caption", "")
            for cell in self.collage.cells
        ) or bool(getattr(self.collage, "merged_cells", {}))
        
        if not has_content:
            return

        captured = self.view._capture_for_undo()
        self.collage.clear()
        if captured:
            self.view._update_history_baseline()

    def update_grid(self, rows: int, cols: int):
        if rows == self.collage.rows and cols == self.collage.columns:
            return
        
        captured = self.view._capture_for_undo()
        try:
            self.collage.update_grid(rows, cols)
        except Exception as exc:
            if captured:
                self.view._discard_latest_snapshot()
            raise exc
        else:
            if captured:
                self.view._update_history_baseline()

    def apply_template(self, name: str):
        try:
            r, c = name.split("x")
            self.view.rows_spin.setValue(int(r))
            self.view.cols_spin.setValue(int(c))
            # Put the actual grid update call here or let the view triggers handle it
            # View likely calls update_grid when spins change if signals are connected
            # But in the original code, _apply_template called _update_grid directly.
            self.update_grid(int(r), int(c))
        except Exception:
            pass
