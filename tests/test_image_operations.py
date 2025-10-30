from PIL import Image, ImageDraw
import logging


def assert_color_close(actual, expected, tolerance=30):
    assert len(actual) == len(expected)
    for component_actual, component_expected in zip(actual, expected, strict=True):
        assert abs(component_actual - component_expected) <= tolerance

from utils.image_operations import (
    apply_operations,
    resize_image,
)


def test_resize_image_preserves_aspect():
    img = Image.new("RGB", (10, 20), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((2, 5, 7, 15), fill=(255, 0, 0))
    resized = resize_image(img, (10, 10))
    assert resized.size == (10, 10)
    assert resized.getpixel((0, 0)) == (255, 255, 255)
    assert_color_close(resized.getpixel((5, 5)), (255, 0, 0))


def test_resize_image_detects_background_colour():
    img = Image.new("RGB", (20, 10), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle((5, 2, 15, 8), fill=(0, 0, 255))

    resized = resize_image(img, (10, 10))

    assert resized.size == (10, 10)
    assert resized.getpixel((0, 0)) == (240, 240, 240)
    assert_color_close(resized.getpixel((5, 5)), (0, 0, 255))


def test_apply_operations_dispatch_and_warns(caplog):
    img = Image.new("RGB", (10, 20), color="red")
    operations = [
        {"type": "resize", "params": {"size": (10, 10), "keep_aspect": True}},
        {"type": "rotate", "params": {"angle": 90}},
        {"type": "unknown", "params": {}},
    ]
    with caplog.at_level(logging.WARNING):
        result = apply_operations(img, operations)
    assert result.size == (10, 10)
    assert "Unknown operation type" in caplog.text

