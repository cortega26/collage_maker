from PIL import Image
import logging

from utils.image_operations import (
    apply_operations,
    resize_image,
)


def test_resize_image_preserves_aspect():
    img = Image.new("RGB", (10, 20), color="red")
    resized = resize_image(img, (10, 10))
    assert resized.size == (5, 10)


def test_apply_operations_dispatch_and_warns(caplog):
    img = Image.new("RGB", (10, 20), color="red")
    operations = [
        {"type": "resize", "params": {"size": (10, 10), "keep_aspect": True}},
        {"type": "rotate", "params": {"angle": 90}},
        {"type": "unknown", "params": {}},
    ]
    with caplog.at_level(logging.WARNING):
        result = apply_operations(img, operations)
    # After resize (5x10) then rotate (10x5)
    assert result.size == (10, 5)
    assert "Unknown operation type" in caplog.text

