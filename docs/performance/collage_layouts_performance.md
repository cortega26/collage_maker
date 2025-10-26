# Collage Layout Performance Baselines

The performance tests assert that core layout lookup helpers stay within the expected latency envelope. The thresholds below are enforced by `tests/performance/test_collage_layouts_perf.py`.

| Benchmark | Loops | Reference µs / call | Max µs / call |
| --- | --- | --- | --- |
| `CollageLayouts.get_layouts_by_tag('grid')` | 10,000 | 0.30 | 5.00 |
| `CollageLayouts.get_layout_names()` | 10,000 | 0.28 | 5.00 |

The reference column captures the observed mean latency on the developer workstation when the baseline was introduced. The max column provides a generous guardrail to avoid flakiness while still surfacing significant regressions.
