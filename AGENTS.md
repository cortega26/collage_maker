# AGENTS

## Scope
These instructions apply to the entire repository.

## High‑Level Guidelines
- Preserve existing functionality; avoid breaking current features.
- Run the full test suite (`pytest`) before committing or merging.
- Follow **DRY**, **KISS**, and **SOLID** principles.
- Favor long‑term maintainability and stability over quick fixes.
- Ensure every change clearly improves the codebase without introducing regressions.

## Tech Stack & Boundaries
- UI toolkit: PySide6 only. Do not introduce or re‑introduce PyQt5 APIs.
  - Use `from PySide6...` imports, `Signal` (not `pyqtSignal`), and `menu.exec(...)` (not `exec_`).
- Imaging: Pillow (PIL). Prefer `Image.Resampling.LANCZOS` for resizing.
- DnD (Tk demo): `tkinterdnd2` is optional; do not make it a hard dependency for tests.
- Do not add new third‑party dependencies without a compelling reason.

## Project Structure (quick map)
- `src/` — primary PySide6 app logic
  - `widgets/` — `CollageWidget`, `CollageCell` (grid editing, merge/split)
  - `managers/` — autosave, performance, recovery helpers
  - `grid_layout.py` — UI‑agnostic layout model with undo/redo
  - `main.py` — main PySide6 entrypoint (loads `ui/style.qss`)
- `ui/` — higher‑level UI shell and QSS theme
  - `collage_canvas.py`, `image_label.py`, `main_window.py`, `style.qss`
- `utils/` — pure helpers: layouts, image processing/operations, validation
- `tests/` — unit/perf tests (no GUI required)
- `collage_app.py` — alternate PySide6 entry; keep working if touched
- `main.py` (root) — simple Tk demo; keep working if touched

## UI/UX Guardrails
- CollageCanvas placement
  - Cells are positioned via explicit geometry (x, y, width, height). Keep
    `_layout_labels` called from `resizeEvent` to update positions.
  - Do not revert to grid coordinates for widget placement.
- Spacing & margins
  - Default collage spacing is 8 px. Use `CollageCanvas.setSpacing(...)` to change.
  - QSS cannot style layouts; set margins/spacing in code (`QLayout.setContentsMargins`, `setSpacing`).
- Styling
  - `ui/style.qss` is the single source of truth for theme. Prefer dynamic
    properties for stateful styling (e.g. `ImageLabel[hasImage="true"]`).
  - Do not reference non‑existent image assets in QSS.

## Reliability & Safety
- Validation
  - Always validate user file paths with `utils.validation`.
  - Reject URLs and unsupported extensions using
    `ImageProcessor.VALID_EXTENSIONS` and `validate_image_path`/
    `validate_output_path`.
- Caching
  - Use `src.cache.ImageCache`. From outside the cache, call `cleanup()` (not
    the private `_cleanup`).
- Threads/workers
  - Avoid blocking the UI thread. For heavy IO/compute, use `src/workers`.
- Logging
  - Use `logging` (no `print`). If modifying logging handlers, prefer a
    rotating handler to avoid unbounded log growth.

## Coding Conventions
- Prefer type hints and small, focused functions. Keep side effects obvious.
- Keep changes minimal and scoped. Do not rename files or move modules unless
  necessary for the task.
- When updating UI modules, keep imports and signal usage consistent with PySide6.

## Testing
- Run: `pytest -q` (fast; no GUI required). All tests must pass.
- Add tests only when there’s a clear, minimal surface to cover new logic.
  - Place UI‑agnostic logic in utils/src so it’s testable.
- Running a subset: `pytest tests/test_grid_layout_manager.py -q`.
- Performance tests in `tests/performance/` assert basic timing only; keep their
  public APIs stable.

## Change Management Checklist
1) Understand scope: confirm target files and impact.
2) Keep UI toolkit consistent (PySide6). No PyQt5 APIs.
3) Use validation helpers for any path/IO change.
4) Mind responsiveness: avoid re‑introducing fixed sizes that block resize.
5) Respect cache encapsulation; use public methods only.
6) Update docs/comments if behavior changes.
7) Run `pytest` and ensure 100% passing before asking to commit/merge.

## Anti‑Patterns (avoid)
- Mixing PyQt5 and PySide6.
- Styling layouts via QSS selectors (ineffective).
- Bypassing validation when handling file paths.
- Using private methods/attributes across modules (e.g. `_cleanup`).
- Introducing blocking operations in the UI thread.
