import os
import sys
import pytest

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.collage_layouts import CollageLayout


def test_cell_dimensions_basic():
    layout = CollageLayout("2x2", [[1,1],[1,1]])
    dims = layout.get_cell_dimensions(100, 100, spacing=0)
    assert len(dims) == 4
    assert dims[0] == {'x':0,'y':0,'width':50,'height':50}


def test_invalid_grid_raises():
    with pytest.raises(ValueError):
        CollageLayout("bad", [])
    with pytest.raises(ValueError):
        CollageLayout("bad", [[1,2],[1]])
    with pytest.raises(ValueError):
        CollageLayout("bad", [[-1]])
