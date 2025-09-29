"""Reusable image manipulation operations.

This module centralizes basic image transformation helpers so they can be
shared across the project.  Functions are intentionally small and pure to
keep them easy to test and to encourage reuse.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging

from PIL import Image, ImageEnhance, ImageFilter


def resize_image(image: Image.Image, size: Tuple[int, int], *, keep_aspect: bool = True) -> Image.Image:
    """Resize ``image`` to ``size``.

    If ``keep_aspect`` is ``True`` the image is resized using
    :py:meth:`~PIL.Image.Image.thumbnail` to preserve the original aspect
    ratio.  Otherwise :py:meth:`~PIL.Image.Image.resize` is used directly.
    """
    if keep_aspect:
        resized = image.copy()
        resized.thumbnail(size, Image.Resampling.LANCZOS)
        return resized
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


def crop_image(image: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
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


_OPERATION_DISPATCH: Dict[str, Any] = {
    "resize": resize_image,
    "rotate": rotate_image,
    "adjust_brightness": adjust_brightness,
    "adjust_contrast": adjust_contrast,
    "crop": crop_image,
    "filter": apply_filter,
}


def apply_operations(image: Image.Image, operations: List[Dict[str, Any]]) -> Image.Image:
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

