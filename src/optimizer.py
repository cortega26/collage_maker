# optimizer.py
"""
Image optimization utilities for Collage Maker.
Provides functions to scale images for display and extract metadata safely.
"""

from typing import Dict
from PySide6.QtCore import Qt, QSize, QFileInfo
from PySide6.QtGui import QImage, QImageReader

import config


class ImageOptimizer:
    """Handles image optimization and metadata extraction."""

    @staticmethod
    def optimize_image(image: QImage, target_size: QSize) -> QImage:
        """
        Scale the image to fit within target_size while maintaining aspect ratio.
        Enforces a maximum display dimension from config.
        """
        # Convert to optimal format if needed
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)

        # Determine scaling factor based on max display dimension
        max_dim = max(target_size.width(), target_size.height())
        if max_dim > config.MAX_DISPLAY_DIMENSION:
            scale = config.MAX_DISPLAY_DIMENSION / max_dim
            scaled_target = QSize(
                int(target_size.width() * scale),
                int(target_size.height() * scale)
            )
        else:
            scaled_target = target_size

        # Perform scaling if needed
        if image.size() != scaled_target:
            image = image.scaled(
                scaled_target,
                aspectMode=Qt.KeepAspectRatio,
                transformMode=Qt.SmoothTransformation
            )

        return image

    @staticmethod
    def process_metadata(file_path: str) -> Dict:
        """
        Extract metadata from an image file: size, format, bit depth, support status, and timestamp.
        """
        reader = QImageReader(file_path)
        supported = reader.canRead()
        if not supported:
            raise IOError(f"Unsupported image format or cannot read file: {file_path}")

        fmt = reader.format().data().decode('utf-8') if reader.format().data() else ''
        image = reader.read()
        depth = image.depth() if image and not image.isNull() else None
        size = reader.size()
        timestamp = QFileInfo(file_path).lastModified()

        return {
            'size': size,
            'format': fmt,
            'depth': depth,
            'supported': supported,
            'timestamp': timestamp
        }
