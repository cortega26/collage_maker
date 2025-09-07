import pytest

from utils.validation import validate_image_path, validate_output_path
from utils.image_processor import ImageProcessor, ImageProcessingError


def test_validate_image_path_rejects_urls(tmp_path):
    with pytest.raises(ValueError):
        validate_image_path("http://example.com/a.png", ImageProcessor.VALID_EXTENSIONS)


def test_validate_image_path_rejects_bad_extension(tmp_path):
    f = tmp_path / "evil.txt"
    f.write_text("not an image")
    with pytest.raises(ValueError):
        validate_image_path(f, ImageProcessor.VALID_EXTENSIONS)


def test_validate_output_path_checks_directory(tmp_path):
    bad_dir = tmp_path / "missing" / "out.png"
    with pytest.raises(ValueError):
        validate_output_path(bad_dir, {".png"})


def test_process_image_invalid_input(tmp_path):
    f = tmp_path / "bad.txt"
    f.write_text("data")
    processor = ImageProcessor()
    with pytest.raises(ImageProcessingError):
        processor.process_image(f, [])
