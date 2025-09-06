def test_utils_package_imports():
    import utils
    assert hasattr(utils, "collage_layouts")
    assert hasattr(utils, "image_processor")

