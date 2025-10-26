from pathlib import Path

from PIL import Image

from utils.image_processor import ImageProcessor


def create_temp_image(tmp_path: Path, size=(10, 10)) -> Path:
    img = Image.new("RGB", size, color="red")
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


def test_resize_without_aspect(tmp_path):
    image_path = create_temp_image(tmp_path, size=(10, 20))
    ops = [{"type": "resize", "params": {"size": (4, 8), "keep_aspect": False}}]
    processor = ImageProcessor()
    result = processor.process_image(image_path, ops)
    assert result.size == (4, 8)


def test_resize_preserves_aspect_when_requested(tmp_path):
    image_path = create_temp_image(tmp_path, size=(10, 20))
    ops = [{"type": "resize", "params": {"size": (10, 10), "keep_aspect": True}}]
    processor = ImageProcessor()
    result = processor.process_image(image_path, ops)
    assert result.size == (5, 10)
