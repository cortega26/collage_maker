"""Performance baselines for collage layout lookups."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PerfBaseline:
    """Configuration for a performance benchmark assertion."""

    loops: int
    max_us_per_call: float
    reference_us_per_call: float


PERF_BASELINES: Final[dict[str, PerfBaseline]] = {
    "get_layouts_by_tag": PerfBaseline(
        loops=10_000,
        max_us_per_call=5.0,
        reference_us_per_call=0.30,
    ),
    "get_layout_names": PerfBaseline(
        loops=10_000,
        max_us_per_call=5.0,
        reference_us_per_call=0.28,
    ),
}
