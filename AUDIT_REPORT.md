# Collage Maker Quality Audit — 2025-03-18

## Scope & Methodology
- **Requested focus**: holistic review of code quality/maintainability, architecture, performance, testing, and UX/UI + accessibility.
- **Artifacts inspected**: primary PySide6 application (`src/main.py`, `src/widgets/*`, `src/managers/*`), imaging utilities (`utils/`), UI shell components (`ui/`), and automated tests (`tests/`).
- **Tooling**: static inspection, repository history review, and spot execution of lightweight AST helpers (no binaries added).

## Findings

### Code Quality & Maintainability
1. **Overgrown control-panel factory (High)** – `MainWindow._create_control_panel` packs 221 lines of widget construction, inline QSS, signal wiring, and state mutation into a single method, making it hard to test or reason about (`src/main.py` lines 118-338). Breaking it into focused builders (e.g., grid controls, caption controls, wiring) would lower cyclomatic complexity and enable isolated tests.
2. **Non-rotating file logging (Medium)** – `logging.basicConfig` wires a `FileHandler` that writes `collage_maker.log` beside the binary with no rotation strategy (`src/main.py` lines 41-49). This violates 12-Factor logging guidance and risks filling user disks; prefer stderr streaming plus opt-in rotating handlers.
3. **Export path bypasses validators (High)** – `_export_collage` accepts whatever `_select_save_path` returns and writes directly via `QImage.save`, never invoking `utils.validation.validate_output_path` (`src/main.py` lines 622-714). Malformed paths slip through and duplicate extensions get silently appended.
4. **Chatty UI logging (Low)** – High-frequency UI events (`CollageCell.setImage`, paint cycles) emit `logging.info`, flooding logs during normal use (`src/widgets/cell.py` lines 117-192). Demote to debug level or gate behind sampling to keep logs actionable.

### Architecture & Boundaries
1. **UI owns domain logic (High)** – `MainWindow` drives autosave snapshots, undo/redo history, export rendering, and color-application rules directly, rather than delegating to services (`src/main.py` lines 414-793). This tight coupling complicates reuse (e.g., CLI exporter) and makes unit isolation difficult.
2. **Global singletons obscure dependencies (Medium)** – Modules rely on `src.cache.image_cache` and the module-level `_PROCESSOR = ImageProcessor()` (`ui/image_label.py` lines 1-103, `src/cache.py` lines 16-74), hindering substitution in tests and leading to implicit shared state.
3. **Autosave payloads embed full pixmaps (Medium)** – `CollageWidget.serialize_for_autosave` base64-encodes every original pixmap, inflating autosave files and recovery time (`src/widgets/collage.py` lines 166-205). Consider storing references plus incremental diffs instead.

### Performance
1. **Repeated pixmap scaling (High)** – Each paint pass rescales the full pixmap in `_draw_image`, creating a new `QPixmap` even when geometry is unchanged (`src/widgets/cell.py` lines 186-193). Cache scaled variants keyed by target size to avoid redundant allocations during hover/resize.
2. **UI-thread decoding for bulk add (High)** – `_add_images` loops over `QImageReader` and optimization synchronously on the main thread (`src/main.py` lines 745-784), freezing the UI when importing large batches. Move decoding/optimization onto workers (`src/workers.py`) and stream results back.
3. **Process pools leak workers (Medium)** – `ImageProcessor.process_batch` lazily creates a `ProcessPoolExecutor` but never shuts it down (`utils/image_processor.py` lines 215-277). Long-running sessions accumulate orphaned processes and memory.
4. **File logging hot path** – Writing every UI interaction to disk magnifies the logging issue above, compounding I/O overhead during drag/drop sessions.

### Testing & CI
1. **Coverage gaps for core UI (High)** – No automated tests exercise `MainWindow`, undo/redo flows, or save/export logic; regressions would slip through unnoticed.
2. **Performance tests assert tautologies (Low)** – The performance micro-bench only asserts that runtime is `> 0`, providing no guard against slowdowns (`tests/performance/test_collage_layouts_perf.py` lines 10-25). Track thresholds or trend metrics instead.
3. **Global singletons hamper testing (Medium)** – Module-level caches/processors make it difficult to inject fakes in tests, pushing teams toward integration tests instead of targeted unit coverage.

### UX/UI & Accessibility
1. **Fixed-height control surface (Medium)** – The toolbar frame is hard-clamped to 118 px, causing overflow when system fonts scale for accessibility (`src/main.py` lines 118-238). Adopt layout-driven sizing and allow wrapping for smaller windows.
2. **Save dialog lacks accessible metadata (Medium)** – Controls created in `_prompt_save_options` omit `setAccessibleName`/`description`, and slider ranges are unlabeled, so assistive tech cannot announce purpose or value (`src/main.py` lines 653-695).
3. **Color-only affordances (Medium)** – Stroke/fill color buttons immediately open dialogs without textual state; users with color-vision deficiencies cannot confirm selections without visual cues (`src/main.py` lines 266-337).
4. **Drag-and-drop instructions not exposed to screen readers (Low)** – `ImageLabel` relies on placeholder text and never sets an accessible description, so the “Drag an image here” affordance is lost for AT users (`ui/image_label.py` lines 16-135).

## Recommendations
- Refactor the control panel into composable widgets/services, extract autosave/export logic into dedicated managers, and introduce dependency injection points for caches/processors.
- Replace direct `QImage` disk writes with a validated `utils.validation.validate_output_path` pipeline before export, and normalize logging to structured stdout with optional rotation.
- Offload heavy imaging work to background workers, cache scaled pixmaps, and ensure executors are explicitly shut down.
- Expand automated coverage around undo/redo, export, and accessibility behaviors; strengthen performance assertions with thresholds.
- Audit UI components for accessibility: remove fixed heights, add accessible names/descriptions, and provide textual feedback for color choices.

---

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
