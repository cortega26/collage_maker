# Collage Maker E2E Audit — 2025-02-14

## Executive Summary
- The PySide6 front end ships several regressions that block core workflows (caption tools, Add Images, grid resizing) and undermine export quality.
- Backend helpers (autosave, image pipeline) are partially integrated: saved state lacks payloads, output paths skip validation, and batch workers report false positives.
- Image fidelity is at risk because cell-level caching overwrites originals with downscaled pixmaps, so “Save Original” currently produces lossy results.
- Testing could not be exercised in this environment (`python` unavailable to the provided shell), so current CI status is unknown.

## Architecture Snapshot
- **UI layer**: Two entry points (`main.py`, `collage_app.py`) with widgets under `src/widgets/` and a separate legacy canvas in `ui/`.
- **State/services**: Autosave, performance, and recovery managers in `src/managers/`; persistent caches via `src/cache.py`.
- **Pure helpers**: Layout modeling (`src/grid_layout.py`), imaging utilities under `utils/`, and Qt style tokens in `src/style_tokens.py`.
- **Tests**: `pytest` suite covering managers, layouts, cache, and imaging; performance micro-benchmarks in `tests/performance/`.

## Frontend Findings
- **Caption panel imports missing** – `QPlainTextEdit`, `QFontComboBox`, and `QColorDialog` are used but never imported, so opening the panel raises `NameError` (`src/main.py:9`).  
- **Caption panel never added to UI** – `_create_caption_panel()` is unused; users cannot reach the new controls (`src/main.py:195`).
- **Add Images fails when run via `python src/main.py`** – the handler performs `from .optimizer import ImageOptimizer`, which breaks when the module runs as `__main__` (`src/main.py:513`).
- **Changing grid size wipes content** – `CollageWidget.update_grid()` rebuilds the layout without reapplying cell pixmaps/captions, dropping all work (`src/widgets/collage.py:199`).
- **Original-image export is lossy** – `CollageCell.setImage()` writes the optimized pixmap into `original_pixmap`, and the cache stores the same scaled asset, so `_save_original` emits degraded images (`src/widgets/cell.py:99`, `src/widgets/cell.py:491`).
- **Global cache keyed only by file path** – subsequent loads of the same file reuse the first cell’s scaled pixmap, so larger cells upscale a downsampled asset (`src/widgets/cell.py:462`).
- **Autosave timer path missing** – the Qt canvas auto-save writes to `temp/autosave_collage.tmp` without creating the directory, so saves fail silently (`ui/collage_canvas.py:59`).
- **Adjusting canvas spacing has no effect** – `CollageCanvas.setSpacing()` updates spacing but never repositions labels, leaving stale geometry (`ui/collage_canvas.py:359`).
- **Drag-drop bypasses validation/pipeline** – `ImageLabel.setImage()` loads raw pixmaps directly, skipping `utils.validation` and EXIF/resize handling expected project-wide (`ui/image_label.py:56`).
- **Default spacing violates product guardrail** – config still sets `DEFAULT_SPACING = 2` instead of the required 8 px, so newly created `CollageWidget`s render too tight (`src/config.py:10`).
- **Autosave payload is effectively empty** – `MainWindow.get_collage_state()` serializes only row/column counts, so recovery cannot restore user data (`src/main.py:576`).
- **Undo/Redo shortcuts stubbed** – `Ctrl+Z / Ctrl+Shift+Z` are registered but both handlers are `pass`, leaving a broken UX expectation (`src/main.py:329`).

## Backend Findings
- **Output path not validated** – `_save_image()` writes to disk without `validate_output_path`, so malformed or unsafe targets slip through (`utils/image_processor.py:144`).
- **Batch processor reports false success** – `_process_image_job()` returns `False` on failure, but the caller ignores the value and marks the run as successful (`utils/image_processor.py:263`).
- **Process executor lifetime** – `ImageProcessor.process_batch()` lazily creates a `ProcessPoolExecutor` but never shuts it down, leading to orphaned workers on repeated runs (medium risk; `utils/image_processor.py:250`).
- **Autosave/recovery logs but lose data** – Autosave and recovery rely on the minimal state blob noted above, so their successful log messages are misleading (`src/managers/autosave.py:64`, `src/managers/recovery.py:45`).

## Testing & Operations
- Attempted `pytest -q`, but the provided shell lacks a `python` interpreter (`python`/`py` commands return “not found”). Verification still required once tooling is accessible.
- Several JSON autosave artifacts are checked into `src/autosave/`; consider clearing to avoid polluting recovery logic.

## Fix Scoreboard
| ID | Area | Finding | Severity | Status | Owner | Notes |
|----|-------|---------|----------|--------|-------|-------|
| F-01 | UI | Import caption panel dependencies (`src/main.py:9`) | High | Open | — | Blocks caption controls. |
| F-02 | UI | Mount caption panel into layout (`src/main.py:195`) | High | Open | — | Expose caption tooling. |
| F-03 | UI | Fix Add Images import when run as script (`src/main.py:513`) | High | Open | — | Prevent ImportError. |
| F-04 | UI | Preserve cell state during grid resize (`src/widgets/collage.py:199`) | High | Open | — | Avoid data loss on template change. |
| F-05 | Imaging | Store originals separately & key cache by size (`src/widgets/cell.py:99`, `src/widgets/cell.py:491`) | Critical | Open | — | Required for lossless export. |
| F-06 | UI | Ensure temp autosave directory exists (`ui/collage_canvas.py:59`) | Medium | Open | — | Prevent silent autosave failures. |
| F-07 | UI | Re-layout after spacing changes (`ui/collage_canvas.py:359`) | Medium | Open | — | Make spacing control functional. |
| F-08 | UI | Route drag/drop through validated loader (`ui/image_label.py:56`) | Medium | Open | — | Apply shared validation & resizing rules. |
| F-09 | Config | Align default spacing with 8 px requirement (`src/config.py:10`) | Medium | Open | — | Match product spec. |
| B-01 | Backend | Validate output paths before saving (`utils/image_processor.py:144`) | High | Open | — | Guard against invalid destinations. |
| B-02 | Backend | Honor batch worker return codes (`utils/image_processor.py:263`) | High | Open | — | Surface failed conversions. |
| B-03 | Ops | Serialize full collage state for autosave (`src/main.py:576`) | High | Open | — | Make recovery meaningful. |
| QA-01 | Tests | Re-run `pytest` once interpreter access is restored | Medium | Blocked | — | Environment missing `python`. |

## Recommended Next Steps
- Prioritize restoring image fidelity (F-05) and grid preservation (F-04); both directly impact user data.
- Address Add Images import (F-03) and missing caption imports (F-01) to unblock critical UI flows.
- Expand autosave serialization (B-03) and hook validation into all output paths (B-01) before enabling recovery messaging.
- Once fixes land, re-run the full `pytest -q` suite (QA-01) and add regression tests around grid resizing and export to lock in behaviour.
