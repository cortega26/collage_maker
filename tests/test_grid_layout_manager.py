import os
import sys
import json
import pytest

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.grid_layout import GridLayoutManager


def test_merge_rectangular_and_invalid():
    mgr = GridLayoutManager(3, 3)
    # valid rectangular merge
    mgr.merge([(0, 0), (0, 1), (1, 0), (1, 1)])
    merged = [c for c in mgr.cells if c.row == 0 and c.column == 0][0]
    assert merged.row_span == 2 and merged.col_span == 2

    # diagonal merge should fail
    mgr2 = GridLayoutManager(2, 2)
    with pytest.raises(ValueError):
        mgr2.merge([(0, 0), (1, 1)])
    # L-shaped merge should fail
    with pytest.raises(ValueError):
        mgr2.merge([(0, 0), (0, 1), (1, 0)])


def test_split_creates_cells():
    mgr = GridLayoutManager(3, 3)
    mgr.merge([(0, 0), (0, 1), (1, 0), (1, 1)])
    merged_id = max(c.id for c in mgr.cells)
    mgr.split(merged_id, 2, 2)
    assert len(mgr.cells) == 9
    assert all(c.row_span == 1 and c.col_span == 1 for c in mgr.cells)


def test_aspect_and_json_roundtrip():
    mgr = GridLayoutManager(2, 2, gutter=5, padding=1)
    cell_id = mgr.cells[0].id
    mgr.set_aspect(cell_id, aspect_mode="fixed", ratio=(4, 3), fit_mode="fill", align="top")
    layout_json = mgr.to_json()
    data = json.loads(layout_json)
    cell_data = next(cd for cd in data["cells"] if cd["id"] == cell_id)
    assert cell_data["aspectMode"] == "fixed"
    assert cell_data["ratio"] == "4:3"
    assert cell_data["fitMode"] == "fill"
    assert cell_data["align"] == "top"
    assert data["gutter"] == 5 and data["padding"] == 1

    mgr2 = GridLayoutManager.from_json(layout_json)
    assert mgr2.to_json() == layout_json


def test_undo_redo_workflow():
    mgr = GridLayoutManager(2, 2)
    initial = mgr.to_json()
    mgr.merge([(0, 0), (0, 1)])
    merged_json = mgr.to_json()
    mgr.undo()
    assert mgr.to_json() == initial
    mgr.redo()
    assert mgr.to_json() == merged_json

    # aspect change undo/redo
    cell_id = next(c.id for c in mgr.cells if c.row == 0 and c.column == 0)
    mgr.set_aspect(cell_id, aspect_mode="fixed", ratio=(1, 1))
    aspect_json = mgr.to_json()
    mgr.undo()
    assert mgr.to_json() == merged_json
    mgr.redo()
    assert mgr.to_json() == aspect_json

    # split undo/redo
    merged_id = next(c.id for c in mgr.cells if c.row_span > 1 or c.col_span > 1)
    mgr.split(merged_id, 1, 2)
    split_json = mgr.to_json()
    mgr.undo()
    assert mgr.to_json() == aspect_json
    mgr.redo()
    assert mgr.to_json() == split_json
