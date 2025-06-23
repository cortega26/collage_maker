# === Module: optimizer.py ===
"""
Image optimization and metadata extraction.
"""
from PySide6.QtGui import QImageReader, QImage
from PySide6.QtCore import QSize, QFileInfo, Qt

class ImageOptimizer:
    @staticmethod
    def optimize_image(image: QImage, target_size: QSize) -> QImage:
        # Ensure ARGB32 for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        # Scale if too large
        max_dim = max(target_size.width(), target_size.height())
        if max_dim > 2000:
            scale = 2000 / max_dim
            target_size = QSize(int(target_size.width() * scale), int(target_size.height() * scale))
        if image.size() != target_size:
            image = image.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return image

    @staticmethod
    def extract_metadata(file_path: str) -> dict:
        reader = QImageReader(file_path)
        info = QFileInfo(file_path)
        size = reader.size()
        return {
            'size': (size.width(), size.height()),
            'format': reader.format().data().decode(),
            'supported': reader.canRead(),
            'modified': info.lastModified().toString()
        }
