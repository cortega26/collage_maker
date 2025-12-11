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
    QToolButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
)

from .modern_spinbox import ModernSpinBox


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
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Row 1: Actions + Grid
        row1_container = QFrame()
        row1 = QHBoxLayout(row1_container)
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(12)

        self._build_actions(row1)
        
        # Spacer to push Grid to the right (or keep them together, let's keep them together for now but separated by a line)
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #cbd5e1;")
        row1.addWidget(line)

        self._build_grid_controls(row1)
        row1.addStretch() # Push everything to left or Keep compact?
        # Actually user wants to use space. Let's add stretch at the end.
        
        layout.addWidget(row1_container)

        # Separator between rows
        h_line = QFrame()
        h_line.setFrameShape(QFrame.HLine)
        h_line.setFrameShadow(QFrame.Sunken)
        h_line.setStyleSheet("color: #cbd5e1;")
        layout.addWidget(h_line)

        # Row 2: Captions
        row2_container = QFrame()
        row2 = QHBoxLayout(row2_container)
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(12)
        
        self._build_caption_controls(row2)
        layout.addWidget(row2_container)

    # Removed _add_separator helper as we inline specific ones now
    
    def _build_grid_controls(self, parent_layout: QHBoxLayout) -> None:
        # Container Widget for Grid
        container = QFrame()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        control_height = 32  # Standard height

        # Rows
        layout.addWidget(QLabel("Rows:"))
        self._rows_spin = ModernSpinBox()
        self._rows_spin.setRange(1, 10)
        self._rows_spin.setValue(self._grid_defaults.rows)
        self._rows_spin.setFixedWidth(70)
        self._rows_spin.setToolTip("Rows")
        layout.addWidget(self._rows_spin)

        # Columns
        layout.addWidget(QLabel("Cols:"))
        self._cols_spin = ModernSpinBox()
        self._cols_spin.setRange(1, 10)
        self._cols_spin.setValue(self._grid_defaults.columns)
        self._cols_spin.setFixedWidth(70)
        self._cols_spin.setToolTip("Columns")
        layout.addWidget(self._cols_spin)

        # Template
        self._template_combo = QComboBox()
        self._template_combo.addItems(self._grid_defaults.templates)
        self._template_combo.setFixedHeight(control_height)
        self._template_combo.setFixedWidth(80)
        self._template_combo.currentTextChanged.connect(self.templateSelected.emit)
        layout.addWidget(self._template_combo)

        # Update Button
        update_btn = QPushButton("🔄")
        update_btn.setToolTip("Update Grid")
        update_btn.setFixedHeight(control_height)
        update_btn.setFixedWidth(control_height)
        update_btn.clicked.connect(self.updateGridRequested.emit)
        layout.addWidget(update_btn)
        
        parent_layout.addWidget(container)

    def _build_actions(self, parent_layout: QHBoxLayout) -> None:
        container = QFrame()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        control_height = 32

        # Primary Action: Add Images (Icon + Text)
        add_btn = QPushButton("📷 Add")
        add_btn.setFixedHeight(control_height)
        add_btn.clicked.connect(self.addImagesRequested.emit)
        layout.addWidget(add_btn)

        # Secondary Actions (Icon Only)
        actions = [
            ("💾", "Save", self.saveRequested.emit),
            ("🔗", "Merge", self.mergeRequested.emit),
            ("✂️", "Split", self.splitRequested.emit),
            ("🗑️", "Clear", self.clearRequested.emit),
        ]

        for icon, tooltip, signal in actions:
            btn = QPushButton(icon)
            btn.setToolTip(tooltip)
            btn.setFixedHeight(control_height)
            btn.setFixedWidth(control_height + 4) # Almost square
            btn.clicked.connect(signal)
            layout.addWidget(btn)
        
        parent_layout.addWidget(container)

    def _build_caption_controls(self, parent_layout: QHBoxLayout) -> None:
        container = QFrame()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        control_height = 32

        # Font Combo (No Label, just the combo)
        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentText(self._caption_defaults.font_family)
        self._font_combo.setFixedHeight(control_height)
        self._font_combo.setMinimumWidth(120)
        self._font_combo.currentFontChanged.connect(lambda _: self._emit_caption_change())
        layout.addWidget(self._font_combo)

        # Size
        layout.addWidget(QLabel("Size:"))
        self._font_size_spin = ModernSpinBox()
        self._font_size_spin.setRange(8, 120)
        self._font_size_spin.setValue(self._caption_defaults.font_size)
        self._font_size_spin.setFixedWidth(70)
        self._font_size_spin.valueChanged.connect(self.fontSizeSpinChanged.emit)
        layout.addWidget(self._font_size_spin)

        # Stroke Width
        layout.addWidget(QLabel("Stroke:"))
        self._stroke_width_spin = ModernSpinBox()
        self._stroke_width_spin.setRange(0, 16)
        self._stroke_width_spin.setValue(self._caption_defaults.stroke_width)
        self._stroke_width_spin.setFixedWidth(70)
        self._stroke_width_spin.valueChanged.connect(lambda _: self._emit_caption_change())
        layout.addWidget(self._stroke_width_spin)

        # Toggles
        self._top_visible_chk = QCheckBox("Top")
        self._top_visible_chk.setChecked(self._caption_defaults.show_top)
        
        self._bottom_visible_chk = QCheckBox("Bottom")
        self._bottom_visible_chk.setChecked(self._caption_defaults.show_bottom)
        
        self._uppercase_chk = QCheckBox("Uppercase")
        self._uppercase_chk.setChecked(self._caption_defaults.uppercase)
        self._uppercase_chk.setToolTip("Convert to Uppercase")

        layout.addWidget(self._top_visible_chk)
        layout.addWidget(self._bottom_visible_chk)
        layout.addWidget(self._uppercase_chk)

        # Colors (Icon buttons)
        self._stroke_btn = QPushButton("Stroke")
        self._stroke_btn.setToolTip("Stroke Color")
        self._stroke_btn.setFixedHeight(control_height)
        self._stroke_btn.clicked.connect(lambda: self.colorPickRequested.emit("stroke"))
        
        self._fill_btn = QPushButton("Fill")
        self._fill_btn.setToolTip("Fill Color")
        self._fill_btn.setFixedHeight(control_height)
        self._fill_btn.clicked.connect(lambda: self.colorPickRequested.emit("fill"))
        
        layout.addWidget(self._stroke_btn)
        layout.addWidget(self._fill_btn)

        # Connect toggles
        for checkbox in (self._top_visible_chk, self._bottom_visible_chk, self._uppercase_chk):
             checkbox.toggled.connect(lambda _: self._emit_caption_change())

        parent_layout.addWidget(container, stretch=1)

    def _emit_caption_change(self) -> None:
        self.captionSettingsChanged.emit()


__all__ = [
    "CaptionDefaults",
    "ControlPanel",
    "GridDefaults",
]
