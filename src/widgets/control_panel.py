"""Control panel widget for the main Collage Maker window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFontComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)


@dataclass(frozen=True)
class GridDefaults:
    """Configuration for the grid controls."""

    rows: int
    columns: int
    templates: Tuple[str, ...]


@dataclass(frozen=True)
class CaptionDefaults:
    """Configuration for the caption controls."""

    font_family: str
    font_size: int
    stroke_width: int
    uppercase: bool
    show_top: bool
    show_bottom: bool


class ControlPanel(QFrame):
    """Toolbar that exposes grid, action, and caption controls."""

    addImagesRequested = Signal()
    mergeRequested = Signal()
    splitRequested = Signal()
    clearRequested = Signal()
    saveRequested = Signal()
    updateGridRequested = Signal()
    templateSelected = Signal(str)
    captionSettingsChanged = Signal()
    fontSizeSliderChanged = Signal(int)
    fontSizeSpinChanged = Signal(int)
    colorPickRequested = Signal(str)

    def __init__(
        self,
        *,
        grid_defaults: GridDefaults,
        caption_defaults: CaptionDefaults,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._grid_defaults = grid_defaults
        self._caption_defaults = caption_defaults

        self.setObjectName("controlPanel")
        self.setProperty("compact", "true")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build_layout()

    # Public control accessors -------------------------------------------------
    @property
    def rows_spin(self) -> QSpinBox:
        return self._rows_spin

    @property
    def cols_spin(self) -> QSpinBox:
        return self._cols_spin

    @property
    def template_combo(self) -> QComboBox:
        return self._template_combo

    @property
    def top_checkbox(self) -> QCheckBox:
        return self._top_visible_chk

    @property
    def bottom_checkbox(self) -> QCheckBox:
        return self._bottom_visible_chk

    @property
    def font_combo(self) -> QFontComboBox:
        return self._font_combo

    @property
    def font_size_slider(self) -> QSlider:
        return self._font_size_slider

    @property
    def font_size_spin(self) -> QSpinBox:
        return self._font_size_spin

    @property
    def stroke_width_spin(self) -> QSpinBox:
        return self._stroke_width_spin

    @property
    def stroke_button(self) -> QPushButton:
        return self._stroke_btn

    @property
    def fill_button(self) -> QPushButton:
        return self._fill_btn

    @property
    def uppercase_checkbox(self) -> QCheckBox:
        return self._uppercase_chk

    # Layout builders ---------------------------------------------------------
    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self._build_grid_row(layout)
        self._build_action_row(layout)
        self._build_caption_rows(layout)

    def _build_grid_row(self, parent_layout: QVBoxLayout) -> None:
        control_height = 36

        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, 10)
        self._rows_spin.setValue(self._grid_defaults.rows)
        self._rows_spin.setFixedHeight(control_height)
        self._rows_spin.setMaximumWidth(90)
        self._rows_spin.setAccessibleName("Row Count")

        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, 10)
        self._cols_spin.setValue(self._grid_defaults.columns)
        self._cols_spin.setFixedHeight(control_height)
        self._cols_spin.setMaximumWidth(90)
        self._cols_spin.setAccessibleName("Column Count")

        self._template_combo = QComboBox()
        self._template_combo.addItems(self._grid_defaults.templates)
        self._template_combo.setAccessibleName("Templates")
        self._template_combo.setFixedHeight(control_height)
        self._template_combo.setMinimumWidth(140)
        self._template_combo.currentTextChanged.connect(self.templateSelected.emit)

        update_btn = QPushButton("Update Grid")
        update_btn.setFixedHeight(control_height)
        update_btn.setAccessibleName("Update Grid")
        update_btn.clicked.connect(self.updateGridRequested.emit)

        grid_row = QGridLayout()
        grid_row.setVerticalSpacing(6)
        grid_row.setHorizontalSpacing(12)
        grid_row.addWidget(QLabel("Rows:"), 0, 0)
        grid_row.addWidget(self._rows_spin, 0, 1)
        grid_row.addWidget(QLabel("Cols:"), 0, 2)
        grid_row.addWidget(self._cols_spin, 0, 3)
        grid_row.addWidget(QLabel("Template:"), 0, 4)
        grid_row.addWidget(self._template_combo, 0, 5)
        grid_row.addWidget(update_btn, 0, 6)
        grid_row.setColumnStretch(5, 1)
        grid_row.setColumnStretch(6, 0)
        parent_layout.addLayout(grid_row)

    def _build_action_row(self, parent_layout: QVBoxLayout) -> None:
        control_height = 36
        actions = QHBoxLayout()
        actions.setSpacing(8)

        for text, signal in (
            ("Add Images…", self.addImagesRequested.emit),
            ("Merge", self.mergeRequested.emit),
            ("Split", self.splitRequested.emit),
            ("Clear All", self.clearRequested.emit),
            ("Save Collage", self.saveRequested.emit),
        ):
            btn = QPushButton(text)
            btn.setFixedHeight(control_height)
            btn.setAccessibleName(text)
            btn.clicked.connect(signal)
            actions.addWidget(btn)

        actions.addStretch(1)
        parent_layout.addLayout(actions)

    def _build_caption_rows(self, parent_layout: QVBoxLayout) -> None:
        control_height = 36

        self._top_visible_chk = QCheckBox("Show Top")
        self._top_visible_chk.setChecked(self._caption_defaults.show_top)
        self._top_visible_chk.setAccessibleName("Toggle Top Caption")
        self._top_visible_chk.setMinimumHeight(control_height)

        self._bottom_visible_chk = QCheckBox("Show Bottom")
        self._bottom_visible_chk.setChecked(self._caption_defaults.show_bottom)
        self._bottom_visible_chk.setAccessibleName("Toggle Bottom Caption")
        self._bottom_visible_chk.setMinimumHeight(control_height)

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentText(self._caption_defaults.font_family)
        self._font_combo.setFixedHeight(control_height)
        self._font_combo.setMinimumWidth(160)
        self._font_combo.currentFontChanged.connect(
            lambda _: self._emit_caption_change()
        )

        size_label = QLabel("Font Size:")
        size_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        self._font_size_slider = QSlider(Qt.Horizontal)
        self._font_size_slider.setRange(8, 120)
        self._font_size_slider.setValue(self._caption_defaults.font_size)
        self._font_size_slider.setFixedHeight(control_height)
        self._font_size_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._font_size_slider.valueChanged.connect(self.fontSizeSliderChanged.emit)

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 120)
        self._font_size_spin.setValue(self._caption_defaults.font_size)
        self._font_size_spin.setFixedHeight(control_height)
        self._font_size_spin.setMaximumWidth(80)
        self._font_size_spin.valueChanged.connect(self.fontSizeSpinChanged.emit)

        size_unit = QLabel("px")
        size_unit.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self._stroke_width_spin = QSpinBox()
        self._stroke_width_spin.setRange(0, 16)
        self._stroke_width_spin.setValue(self._caption_defaults.stroke_width)
        self._stroke_width_spin.setFixedHeight(control_height)
        self._stroke_width_spin.setMaximumWidth(80)
        self._stroke_width_spin.valueChanged.connect(
            lambda _: self._emit_caption_change()
        )

        self._stroke_btn = QPushButton("Stroke Color")
        self._stroke_btn.setFixedHeight(control_height)
        self._stroke_btn.clicked.connect(lambda: self.colorPickRequested.emit("stroke"))

        self._fill_btn = QPushButton("Fill Color")
        self._fill_btn.setFixedHeight(control_height)
        self._fill_btn.clicked.connect(lambda: self.colorPickRequested.emit("fill"))

        self._uppercase_chk = QCheckBox("UPPERCASE")
        self._uppercase_chk.setChecked(self._caption_defaults.uppercase)
        self._uppercase_chk.setAccessibleName("Toggle Uppercase Captions")
        self._uppercase_chk.setMinimumHeight(control_height)

        for checkbox in (
            self._top_visible_chk,
            self._bottom_visible_chk,
            self._uppercase_chk,
        ):
            checkbox.toggled.connect(lambda _: self._emit_caption_change())

        caption_layout = QGridLayout()
        caption_layout.setHorizontalSpacing(10)
        caption_layout.setVerticalSpacing(6)
        caption_layout.addWidget(self._top_visible_chk, 0, 0)
        caption_layout.addWidget(self._bottom_visible_chk, 0, 1)
        caption_layout.addWidget(QLabel("Font:"), 0, 2)
        caption_layout.addWidget(self._font_combo, 0, 3)
        caption_layout.addWidget(size_label, 0, 4)
        caption_layout.addWidget(self._font_size_slider, 0, 5, 1, 3)
        caption_layout.addWidget(self._font_size_spin, 0, 8)
        caption_layout.addWidget(size_unit, 0, 9)
        caption_layout.addWidget(QLabel("Stroke:"), 1, 0)
        caption_layout.addWidget(self._stroke_width_spin, 1, 1)
        caption_layout.addWidget(self._stroke_btn, 1, 2)
        caption_layout.addWidget(self._fill_btn, 1, 3)
        caption_layout.addWidget(self._uppercase_chk, 1, 4)
        caption_layout.setColumnStretch(3, 1)
        caption_layout.setColumnStretch(5, 3)
        caption_layout.setColumnStretch(9, 1)

        parent_layout.addLayout(caption_layout)

    def _emit_caption_change(self) -> None:
        self.captionSettingsChanged.emit()


__all__ = [
    "CaptionDefaults",
    "ControlPanel",
    "GridDefaults",
]
