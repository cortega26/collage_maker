import os
import sys
import timeit

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from utils.collage_layouts import CollageLayouts


def test_get_layouts_by_tag_perf():
    CollageLayouts._invalidate_caches()
    loops = 10000
    duration = timeit.timeit(
        "CollageLayouts.get_layouts_by_tag('grid')",
        globals={'CollageLayouts': CollageLayouts},
        number=loops,
    )
    print(f"get_layouts_by_tag {duration/loops*1e6:.3f} us per call over {loops} loops")
    assert duration > 0


def test_get_layout_names_perf():
    CollageLayouts._invalidate_caches()
    loops = 10000
    duration = timeit.timeit(
        "CollageLayouts.get_layout_names()",
        globals={'CollageLayouts': CollageLayouts},
        number=loops,
    )
    print(f"get_layout_names {duration/loops*1e6:.3f} us per call over {loops} loops")
    assert duration > 0
