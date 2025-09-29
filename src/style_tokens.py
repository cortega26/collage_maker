"""Lightweight design system tokens and QSS generator.

Use these tokens to keep colors, typography, spacing and component styles
consistent across the UI. The QSS generated here is applied on top of any
static `ui/style.qss` so tokens can override defaults.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Colors:
    text: str = "#111827"        # Gray-900
    text_muted: str = "#6b7280"   # Gray-500
    background: str = "#f9fafb"   # Gray-50
    surface: str = "#ffffff"      # White
    border: str = "#e5e7eb"       # Gray-200
    focus: str = "#1d4ed8"        # Blue-700
    primary: str = "#0a58ca"      # Accessible blue
    primary_hover: str = "#094db3"
    primary_pressed: str = "#083a9b"


@dataclass(frozen=True)
class Typography:
    font_family: str = '"Segoe UI", "Inter", system-ui'
    font_size_pt: int = 11


@dataclass(frozen=True)
class Radius:
    sm: int = 4
    md: int = 6
    lg: int = 8


SPACING_UNIT = 4  # px


def space(n: int) -> int:
    """Return spacing in pixels based on a 4px scale."""
    return max(0, int(n) * SPACING_UNIT)


def build_qss(colors: Colors = Colors(), typo: Typography = Typography(), radius: Radius = Radius()) -> str:
    """Return QSS string using design tokens."""
    return f"""
/* Base */
QWidget {{
    font-family: {typo.font_family};
    font-size: {typo.font_size_pt}pt;
    color: {colors.text};
}}

QMainWindow {{
    background-color: {colors.background};
}}

QLabel {{ color: {colors.text}; }}
QToolTip {{ color: {colors.text}; background-color: {colors.surface}; border: 1px solid {colors.border}; }}

/* Buttons */
QPushButton {{
    background-color: {colors.primary};
    color: #ffffff;
    border: 1px solid {colors.primary};
    border-radius: {radius.md}px;
    padding: {space(1)}px {space(3)}px;
    min-height: 32px;
}}
QPushButton:hover {{ background-color: {colors.primary_hover}; border-color: {colors.primary_hover}; }}
QPushButton:pressed {{ background-color: {colors.primary_pressed}; border-color: {colors.primary_pressed}; }}
QPushButton:disabled {{ background-color: #e5e7eb; border-color: #e5e7eb; color: #9ca3af; }}
QPushButton:focus {{ outline: none; border: 2px solid {colors.focus}; }}

/* Inputs */
QComboBox {{
    background-color: {colors.surface};
    color: {colors.text};
    border: 1px solid {colors.border};
    border-radius: {radius.md}px;
    padding: {space(1)}px {space(2)}px;
    min-width: 140px;
    min-height: 32px;
}}
QComboBox::drop-down {{ width: 22px; border-left: 1px solid {colors.border}; }}
QComboBox QAbstractItemView {{ border: 1px solid {colors.border}; selection-background-color: {colors.primary}; selection-color: #ffffff; }}

/* Spin boxes and line edits */
QAbstractSpinBox, QLineEdit {{
    background-color: {colors.surface};
    color: {colors.text};
    border: 1px solid {colors.border};
    border-radius: {radius.md}px;
    padding: {space(1)}px {space(2)}px;
    min-height: 32px;
    selection-background-color: {colors.focus};
    selection-color: #ffffff;
}}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    background: {colors.surface};
    border-left: 1px solid {colors.border};
    width: 22px;
}}
QAbstractSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; }}
QAbstractSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; }}

/* Explicit spinbox text field styling (some platforms require child selector) */
QSpinBox {{
    background-color: {colors.surface};
    color: {colors.text};
    border: 1px solid {colors.border};
    border-radius: {radius.md}px;
    padding: {space(1)}px {space(5)}px {space(1)}px {space(2)}px; /* leave space for arrows */
    min-height: 32px;
}}
QSpinBox QLineEdit {{
    background: transparent;
    color: {colors.text};
    selection-background-color: {colors.focus};
    selection-color: #ffffff;
}}
QSpinBox:disabled {{ color: {colors.text_muted}; }}

/* Cards */
QFrame#card {{
    background-color: {colors.surface};
    border: 1px solid {colors.border};
    border-radius: {radius.lg}px;
    padding: {space(3)}px;
}}

/* Image frame (CollageCell) */
CollageCell {{
    border: 1px solid {colors.border};
    border-radius: {radius.md}px;
    background-color: {colors.surface};
}}
CollageCell:focus {{ border: 2px solid {colors.focus}; }}
"""


def _dark_colors() -> Colors:
    return Colors(
        text="#e5e7eb",
        text_muted="#9ca3af",
        background="#0f172a",  # slate-900
        surface="#111827",
        border="#334155",
        focus="#60a5fa",
        primary="#60a5fa",
        primary_hover="#3b82f6",
        primary_pressed="#2563eb",
    )


def apply_tokens(app, *, theme: str = "light", colors: Colors | None = None, typo: Typography = Typography(), radius: Radius = Radius()) -> None:
    """Append token-generated QSS to the current application style sheet.

    Args:
        theme: 'light' (default) or 'dark'. Ignored if explicit colors provided.
        colors: optional Colors override. If None, chosen by theme.
    """
    chosen = colors or (_dark_colors() if str(theme).lower() == "dark" else Colors())
    qss = build_qss(chosen, typo, radius)
    app.setStyleSheet((app.styleSheet() or "") + "\n" + qss)


def get_colors(*, theme: str = "light", colors: Colors | None = None) -> Colors:
    """Return the effective Colors object given a theme or explicit override.

    This mirrors the selection logic in ``apply_tokens`` so code can retrieve
    the active palette and, for instance, set widget-level palettes.
    """
    if colors:
        return colors
    return _dark_colors() if str(theme).lower() == "dark" else Colors()
