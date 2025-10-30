# Performance & Web Vitals Summary — October 2024

| Flow | Budget | Observed Risk | Evidence | Recommendation |
| --- | --- | --- | --- | --- |
| Autosave tick | ≤150 ms on UI thread | JSON writes + `time.sleep` retries freeze UI for 100–700 ms per failure, violating INP budgets. | 【F:src/managers/autosave.py†L61-L94】 | Move serialization/retry loop into `Worker`; replace sleeps with timer-based backoff; emit duration metrics. |
| Export (with originals) | ≤250 ms UI blocking before worker dispatch | `_compose_original_image` constructs full-resolution `QImage` synchronously, causing memory spikes and long pauses. | 【F:src/main.py†L779-L817】 | Tile composition in background worker or stream originals to disk incrementally. |
| Add Images | ≤16 ms per drop | Validation skipped; invalid `file://` URIs can block `QImageReader` on UI thread. | 【F:src/main.py†L726-L762】 | Validate paths before reading; preflight using `utils.validation.validate_image_path`. |
| Save dialog | Immediate feedback | `_select_save_path` accepts missing directories, error surfaces late with modal alert. | 【F:src/main.py†L624-L641】 | Validate directories/extensions up front and prompt to create missing folders. |

## Additional Notes
- No Lighthouse/Web Vitals traces provided. Capture desktop/mobile traces after backgrounding autosave/export.
- Add instrumentation: log autosave duration, export composition time, and cache hit rate to confirm improvements.
- Define CI perf gate: reuse `tests/performance/test_collage_layouts_perf.py` metrics, fail when >10% over baseline.【F:tests/performance/test_collage_layouts_perf.py†L10-L51】
