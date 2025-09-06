import os
import sys
from pathlib import Path

import pytest
from PIL import Image

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.image_processor import ImageProcessor


def create_temp_image(tmp_path: Path) -> Path:
    img = Image.new("RGB", (10, 10), color="red")
    path = tmp_path / "img.png"
    img.save(path)
    return path


def test_processing_uses_cache(tmp_path):
    image_path = create_temp_image(tmp_path)
    ops = [{"type": "rotate", "params": {"angle": 90}}]
    processor = ImageProcessor()

    first = processor.process_image(image_path, ops)
    second = processor.process_image(image_path, ops)

    assert first is second  # cached object returned
