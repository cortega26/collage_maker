"""Legacy PySide6 launcher bridging to the shared main window."""
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, Sequence

from PySide6.QtWidgets import QApplication

from src import style_tokens
from src.main import MainWindow
from utils.image_processor import ImageProcessor
from utils.validation import validate_image_path

# Reuse the project-wide rotating logging configuration installed in src.main.
logger = logging.getLogger("collage_maker.legacy_launcher")


def _apply_styles(app: QApplication) -> None:
    """Apply shared QSS + tokenised theme to *app*."""
    qss_path = Path("ui/style.qss")
    if qss_path.exists():
        qss_content = qss_path.read_text(encoding="utf-8")
        
        # Inject absolute path for check icon to resolve relative path issues
        # Convert backslashes to forward slashes for CSS url() compatibility
        icon_path = (Path("src/assets/check_icon.svg").resolve().as_posix())
        qss_content = qss_content.replace("%CHECK_ICON%", icon_path)
        
        arrow_path = (Path("src/assets/arrow_down.svg").resolve().as_posix())
        qss_content = qss_content.replace("%ARROW_DOWN_ICON%", arrow_path)
        
        app.setStyleSheet(qss_content)
        
    theme = os.environ.get("COLLAGE_THEME", "light")
    style_tokens.apply_tokens(app, theme=theme)


def _prefill_images(window: MainWindow, image_paths: Iterable[str]) -> None:
    """Preload validated *image_paths* into the first available cells."""
    safe_paths: list[str] = []
    for raw in image_paths:
        try:
            resolved = validate_image_path(
                raw, ImageProcessor.VALID_EXTENSIONS)
        except ValueError as exc:
            logger.warning("Skipping invalid image %s: %s", raw, exc)
            continue
        safe_paths.append(str(resolved))

    if not safe_paths:
        return

    empties = [cell for cell in window.collage.cells if not getattr(
        cell, "pixmap", None)]
    if not empties:
        logger.info("No empty cells available to preload CLI images.")
        return

    assigned = 0
    for path, cell in zip(safe_paths, empties):
        try:
            cell._load_image(path)
            assigned += 1
        except Exception as exc:  # pragma: no cover - Qt loader errors are UI-driven
            logger.warning("Failed to preload %s: %s", path, exc)

    if assigned < len(safe_paths):
        logger.info("Loaded %d of %d requested images into the collage.",
                    assigned, len(safe_paths))


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the PySide6 UI while keeping CLI compatibility for legacy scripts."""
    image_args = list(sys.argv[1:] if argv is None else argv)
    qt_args = [sys.argv[0], *image_args]

    app = QApplication(qt_args)
    app.setStyle("Fusion")
    _apply_styles(app)

    window = MainWindow()
    _prefill_images(window, image_args)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
