# AGENTS

## Mission & Scope
These instructions govern every change in the repository. Default to preserving the PySide6 desktop experience and the Tk demo at the project root. When trade-offs arise, favor long-term stability, undo-friendly workflows, and responsive UI updates over quick fixes.

## Architecture Snapshot
- **Entry points**
  - `src/main.py`: primary PySide6 app with the unified control panel, undo/redo history, autosave, and export logic.
  - `collage_app.py` & `main.py` (root): legacy/demo launchers; keep functional when touched.
- **Core packages**
  - `src/widgets/`: `CollageWidget` + `CollageCell` (grid editing, drag/drop, merge/split, caption rendering).
  - `src/managers/`: autosave, performance, recovery helpers.
  - `src/grid_layout.py`: UI-agnostic layout model with undo/redo.
  - `ui/`: higher-level shell (CollageCanvas) and QSS.
  - `utils/`: validation, image utilities, layout helpers.
  - `tests/`: unit + perf suites (no GUI required).

## UX & UI Guardrails
- **Unified control panel**
  - Top row = grid configuration (`rows`, `cols`, template) + primary actions (`Add Images`, `Merge`, `Split`, `Clear All`, `Save`).
  - Second row = caption tools (top/bottom toggles, font combo, dedicated font-size slider + spinbox, stroke width, stroke/fill buttons, uppercase toggle).
  - Keep control heights ~30 px, consistent spacing, and visible spinbox arrows. New controls must plug into `_apply_captions_now` and history capture helpers.
- **CollageCanvas (ui/)**
  - Widgets positioned via explicit geometry. Keep `_layout_labels` in resize handlers—never revert to layout-managed positioning.
  - Maintain spacing via runtime code (`setSpacing`, `setContentsMargins`) not QSS.
- **Styling**
  - `ui/style.qss` + `style_tokens.py` define theme. Use dynamic properties (e.g., `CollageCell[selected="true"]`) for stateful styles instead of ad-hoc palettes.
  - When customizing controls, prefer token values from `style_tokens.get_colors`.

## Reliability & Safety
- Always validate file paths with `utils.validation` before IO; reject URLs and unsupported extensions per `ImageProcessor.VALID_EXTENSIONS`.
- Respect cache boundaries: use `src.cache.image_cache` APIs and the public `cleanup()` helper when needed.
- Heavy IO/CPU must leave the UI thread; use workers under `src/workers` where applicable.
- Logging only via the `logging` module. For new handlers prefer rotating or size-bounded logs.
- Autosave/undo: when you mutate collage state, capture history via `_capture_for_undo()` and update `_history_baseline` on success. Restoration flows through `_restore_state`/`CollageWidget.restore_from_serialized`—reuse these helpers.

## Coding Conventions
- PySide6 only (no PyQt5 symbols). Use `Signal`, `menu.exec()`, etc.
- Prefer small, type-hinted functions. Keep side effects obvious and localized.
- Reuse utilities where possible; avoid duplicating logic already in `utils/` or `widgets/`.
- When touching captions, ensure both legacy single-caption and meme-style caption paths remain stable.

## Testing & Tooling
- Default test command: `python -m pytest -q` (headless). Add focused tests only when new logic is deterministic and UI-agnostic.
- Performance contracts (tests/performance) must remain backward-compatible.
- Before requesting merge/commit, confirm the undo stack and autosave flow still work (sanity run from UI recommended when feasible).

## Dependencies
- PySide6, Pillow, and psutil are required runtime dependencies. Do not add new third-party packages without strong justification.
- Keep `.venv/` or other virtual-env folders out of version control.

## Change Checklist
1. Understand target files and ripple effects.
2. Keep UI responsive (no blocking calls on the main thread).
3. Validate user inputs and file paths.
4. Wire new stateful controls into autosave/undo helpers.
5. Update docs/comments when behavior changes.
6. Run the appropriate pytest subset (or full suite) and ensure green before handing off work.

## Anti-patterns
- Mixing PyQt5 & PySide6 APIs.
- Styling layouts via QSS selectors (ineffective).
- Bypassing validation/caches or accessing private helpers (e.g., `image_cache._cleanup`).
- Introducing blocking operations or large synchronous file IO in UI handlers.
- Forgetting to refresh history/autosave snapshots after mutating the collage.
