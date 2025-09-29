"""PySide6 entrypoint: launches the main application window from src.main."""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication

try:
    from src.main import MainWindow
except Exception as exc:
    # Provide a clear error if imports fail due to PYTHONPATH issues
    raise RuntimeError("Failed to import src.main.MainWindow. Ensure project root is on PYTHONPATH.") from exc


def main() -> int:
    app = QApplication(sys.argv)
    qss = Path('ui/style.qss')
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding='utf-8'))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

