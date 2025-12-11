"""PySide6 entrypoint: launches the main application window from src.main.

Applies static QSS (ui/style.qss) and design tokens (src/style_tokens.py)
so that UI tweaks like compact toolbars take effect even when starting from
this root entrypoint.
"""

import os
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication

try:
    from src.main import MainWindow
    from src import style_tokens
except Exception as exc:
    # Provide a clear error if imports fail due to PYTHONPATH issues
    raise RuntimeError("Failed to import src modules. Ensure project root is on PYTHONPATH.") from exc


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Force-enable Fusion for consistent QSS rendering
    # Load static QSS first
    qss = Path('ui/style.qss')
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding='utf-8'))
    # Overlay design tokens (enables compact toolbar and theme colors)
    theme = os.environ.get('COLLAGE_THEME', 'light')
    style_tokens.apply_tokens(app, theme=theme)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
