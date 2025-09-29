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
    text: str = "#1f2937"
    text_muted: str = "#6b7280"
    background: str = "#f7f8fa"
    surface: str = "#ffffff"
    border: str = "#e5e7eb"
    focus: str = "#1d4ed8"
    primary: str = "#0a58ca"
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


def apply_tokens(app, *, colors: Colors = Colors(), typo: Typography = Typography(), radius: Radius = Radius()) -> None:
    """Append token-generated QSS to the current application style sheet."""
    qss = build_qss(colors, typo, radius)
    app.setStyleSheet((app.styleSheet() or "") + "\n" + qss)

