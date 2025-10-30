"""Reusable image manipulation operations.

This module centralizes basic image transformation helpers so they can be
shared across the project.  Functions are intentionally small and pure to
keep them easy to test and to encourage reuse.
"""

from __future__ import annotations

import logging
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter

ColorValue = int | tuple[int, ...]


def _colors_close(a: ColorValue, b: ColorValue, *, tolerance: int = 3) -> bool:
    """Return ``True`` when ``a`` and ``b`` represent nearly identical colours."""

    if isinstance(a, tuple) and isinstance(b, tuple):
        if len(a) != len(b):
            return False
        return all(
            abs(component_a - component_b) <= tolerance
            for component_a, component_b in zip(a, b, strict=True)
        )
    if isinstance(a, int) and isinstance(b, int):
        return abs(a - b) <= tolerance
    return a == b


def _default_background(mode: str) -> ColorValue:
    """Return a sensible default background colour for ``mode``."""

    if mode in {"RGB", "P"}:
        return (255, 255, 255)
    if mode == "RGBA":
        return (255, 255, 255, 255)
    if mode == "L":
        return 255
    if mode == "LA":
        return (255, 255)
    try:
        return Image.new(mode, (1, 1), "white").getpixel((0, 0))
    except ValueError:
        return 255


def _detect_background_colour(image: Image.Image) -> ColorValue:
    """Best-effort detection of a uniform background colour for ``image``."""

    width, height = image.size
    if width == 0 or height == 0:
        return _default_background(image.mode)

    corners = [
        image.getpixel((0, 0)),
        image.getpixel((max(width - 1, 0), 0)),
        image.getpixel((0, max(height - 1, 0))),
        image.getpixel((max(width - 1, 0), max(height - 1, 0))),
    ]
    reference = corners[0]
    if all(_colors_close(reference, colour) for colour in corners[1:]):
        return reference

    bands = image.getbands()
    if "A" in bands:
        alpha_index = bands.index("A")
        if all(isinstance(colour, tuple) and colour[alpha_index] == 0 for colour in corners):
            transparent_default = _default_background(image.mode)
            if isinstance(transparent_default, tuple):
                components = list(transparent_default)
                components[alpha_index] = 0
                return tuple(components)
            return transparent_default

    return _default_background(image.mode)


def resize_image(image: Image.Image, size: tuple[int, int], *, keep_aspect: bool = True) -> Image.Image:
    """Resize ``image`` to ``size``.

    When ``keep_aspect`` is ``True`` the original proportions are preserved
    and any leftover space is padded with a background colour instead of
    stretching.  The background attempts to match a uniform edge colour and
    falls back to white when no obvious match exists.
    """

    if keep_aspect:
        resized = image.copy()
        resized.thumbnail(size, Image.Resampling.LANCZOS)
        if resized.size == size:
            return resized

        background_colour = _detect_background_colour(image)
        canvas = Image.new(image.mode, size, background_colour)
        offset_x = (size[0] - resized.width) // 2
        offset_y = (size[1] - resized.height) // 2
        canvas.paste(resized, (offset_x, offset_y))
        return canvas

    return image.resize(size, Image.Resampling.LANCZOS)


def rotate_image(image: Image.Image, angle: float, *, expand: bool = True) -> Image.Image:
    """Rotate ``image`` ``angle`` degrees."""
    return image.rotate(angle, expand=expand, resample=Image.Resampling.BICUBIC)


def adjust_brightness(image: Image.Image, factor: float) -> Image.Image:
    """Return ``image`` with adjusted brightness."""
    enhancer = ImageEnhance.Brightness(image)
    return enhancer.enhance(factor)


def adjust_contrast(image: Image.Image, factor: float) -> Image.Image:
    """Return ``image`` with adjusted contrast."""
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def crop_image(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """Crop ``image`` to ``box``."""
    return image.crop(box)


def apply_filter(image: Image.Image, filter_type: str) -> Image.Image:
    """Apply a predefined filter to ``image``.

    Unrecognised filters fall back to :pydata:`~PIL.ImageFilter.BLUR` to keep
    behaviour stable.
    """
    filters = {
        "blur": ImageFilter.BLUR,
        "sharpen": ImageFilter.SHARPEN,
        "smooth": ImageFilter.SMOOTH,
        "edge_enhance": ImageFilter.EDGE_ENHANCE,
        "detail": ImageFilter.DETAIL,
    }
    if filter_type == "grayscale":
        return image.convert("L").convert("RGB")
    return image.filter(filters.get(filter_type, ImageFilter.BLUR))


_OPERATION_DISPATCH: dict[str, Any] = {
    "resize": resize_image,
    "rotate": rotate_image,
    "adjust_brightness": adjust_brightness,
    "adjust_contrast": adjust_contrast,
    "crop": crop_image,
    "filter": apply_filter,
}


def apply_operations(image: Image.Image, operations: list[dict[str, Any]]) -> Image.Image:
    """Apply a sequence of transformation ``operations`` to ``image``.

    Each operation dictionary must contain a ``type`` key that matches one of
    the keys in :data:`_OPERATION_DISPATCH` and an optional ``params``
    dictionary.  Unknown operation types are ignored with a warning to aid
    debugging while preserving previous behaviour.
    """
    result = image.copy()
    for operation in operations:
        op_type = operation.get("type")
        params = operation.get("params", {})
        func = _OPERATION_DISPATCH.get(op_type)
        if not func:
            logging.warning("Unknown operation type: %s", op_type)
            continue
        result = func(result, **params)
    return result


__all__ = [
    "resize_image",
    "rotate_image",
    "adjust_brightness",
    "adjust_contrast",
    "crop_image",
    "apply_filter",
    "apply_operations",
]

