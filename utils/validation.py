"""Input validation helpers for secure file handling."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Union
from urllib.parse import urlparse


def _has_url_scheme(path_str: str) -> bool:
    """Return True if *path_str* looks like a URL with a scheme.

    Single-letter schemes such as ``"C"`` are treated as drive letters on
    Windows and therefore ignored.
    """
    parsed = urlparse(path_str)
    return bool(parsed.scheme and len(parsed.scheme) > 1)


def validate_image_path(path: Union[str, Path], allowed_exts: Iterable[str]) -> Path:
    """Validate a user-supplied image *path*.

    The path must point to an existing file with an allowed extension and must
    not include a URL scheme.  Returns the resolved ``Path`` object.
    """
    path_str = str(path)
    if _has_url_scheme(path_str):
        raise ValueError("URLs are not allowed")

    p = Path(path_str).expanduser()
    try:
        p = p.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"File does not exist: {path_str}") from exc

    if not p.is_file():
        raise ValueError(f"Not a file: {path_str}")

    if p.suffix.lower() not in {ext.lower() for ext in allowed_exts}:
        raise ValueError(f"Unsupported file extension: {p.suffix}")

    return p


def validate_output_path(path: Union[str, Path], allowed_exts: Iterable[str]) -> Path:
    """Validate an output file *path*.

    Ensures the directory exists, the extension is allowed and the path does not
    contain a URL scheme.  Returns the resolved ``Path``.
    """
    path_str = str(path)
    if _has_url_scheme(path_str):
        raise ValueError("URLs are not allowed")

    p = Path(path_str).expanduser()
    p = p.resolve()

    if not p.parent.exists():
        raise ValueError(f"Directory does not exist: {p.parent}")

    if p.suffix.lower() not in {ext.lower() for ext in allowed_exts}:
        raise ValueError(f"Unsupported file extension: {p.suffix}")

    return p
