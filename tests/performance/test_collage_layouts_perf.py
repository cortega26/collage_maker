import json
import timeit
from pathlib import Path
from typing import Final

from utils.collage_layouts import CollageLayouts

from .perf_baselines import PERF_BASELINES, PerfBaseline

RESULTS_FILENAME: Final[str] = "collage_layouts_perf_metrics.json"


def _run_benchmark(stmt: str, baseline: PerfBaseline) -> float:
    CollageLayouts._invalidate_caches()
    duration = timeit.timeit(
        stmt,
        globals={"CollageLayouts": CollageLayouts},
        number=baseline.loops,
    )
    per_call_us = duration / baseline.loops * 1e6
    return per_call_us


def _record_metric(directory: Path, name: str, value_us: float) -> None:
    metrics_path = directory / RESULTS_FILENAME
    metrics = {}
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics[name] = value_us
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def _assert_perf(name: str, stmt: str) -> float:
    baseline = PERF_BASELINES[name]
    per_call_us = _run_benchmark(stmt, baseline)
    assert (
        per_call_us <= baseline.max_us_per_call
    ), f"{name} took {per_call_us:.3f}us per call, expected ≤ {baseline.max_us_per_call:.2f}us"
    return per_call_us


def test_get_layouts_by_tag_perf(tmp_path):
    per_call_us = _assert_perf(
        "get_layouts_by_tag", "CollageLayouts.get_layouts_by_tag('grid')"
    )
    _record_metric(tmp_path, "get_layouts_by_tag", per_call_us)


def test_get_layout_names_perf(tmp_path):
    per_call_us = _assert_perf("get_layout_names", "CollageLayouts.get_layout_names()")
    _record_metric(tmp_path, "get_layout_names", per_call_us)
