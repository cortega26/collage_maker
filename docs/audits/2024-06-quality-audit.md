# Collage Maker Quality Audit (June 2024)

## Executive Summary
- **Overall posture:** Core grid and cache modules are structured, but the PySide6 entry point remains monolithic and UI-bound, which increases maintenance cost and impedes testing.
- **Priority fixes:** Break up `MainWindow` responsibilities, introduce rotating logging/configurable handlers, and decouple autosave serialization from full-pixmap encoding.
- **Opportunities:** Expand automated tests around UI-free controllers, add asynchronous workers for heavyweight IO, and align accessibility affordances with WCAG 2.1 AA expectations.

## Assessment Approach
Manual inspection of source modules (`src/main.py`, `src/widgets/collage.py`, `src/cache.py`, `collage_app.py`), test suites under `tests/`, and UI styling in `ui/style.qss`. No runtime profiling tools were executed in this pass.

## 1. Code Quality & Maintainability

### Findings
1. **Monolithic `MainWindow` controller** – `_create_control_panel` alone spans ~200 lines, mixing widget creation, style sheets, signals, and business logic, pushing cyclomatic complexity beyond the stated target and complicating reuse.【F:src/main.py†L118-L328】
2. **Global logging with static handlers** – `logging.basicConfig` installs a file handler pointing to `collage_maker.log` without rotation/size limits, risking disk growth and duplicate handler installation when modules are re-imported (not idempotent).【F:src/main.py†L41-L57】
3. **Legacy Tk/PySide hybrid** – `collage_app.py` reimplements core widget logic with divergent defaults (e.g., always-on bold/italic/underline captions) and lacks shared validation, creating dead-code risk and inconsistent behavior between launchers.【F:collage_app.py†L31-L160】

### Recommendations
- Extract control panel construction into dedicated view classes or factory helpers with focused unit tests; move caption synchronization into a presenter/service.
- Replace `basicConfig` with a module-level `getLogger(__name__)` and configure rotating handlers (e.g., `RotatingFileHandler`) via a centralized logging factory exposed by `config`.
- Either deprecate `collage_app.py` with migration notes or refactor it to consume shared widgets/managers to avoid drift.

## 2. Architecture & Boundaries

### Findings
1. **Tight coupling of UI and persistence** – `MainWindow` invokes file dialogs, autosave, history, and optimizer logic directly, leaving no seam for headless automation or service reuse. This impedes scalability (e.g., background workers or API exposure).【F:src/main.py†L212-L399】
2. **Global mutable cache** – `image_cache` is a singleton instantiated at import time. Without dependency injection hooks, swapping strategies (e.g., memory-mapped, disk-backed) or testing eviction is cumbersome.【F:src/cache.py†L16-L72】
3. **Autosave serialization baked into widget** – `CollageWidget.serialize_for_autosave` directly encodes UI state, including base64 pixmaps, binding persistence format to widget internals and hindering alternative front ends.【F:src/widgets/collage.py†L166-L221】

### Recommendations
- Introduce application services (e.g., `CollageController`) that expose undo/autosave/image operations independent of `QWidget` lifecycle.
- Pass caches and managers into widgets via constructors or a lightweight dependency container to enable mocking and alternative implementations.
- Move serialization into a dedicated serializer module that works on a plain data model, allowing different UIs to share persistence.

## 3. Performance

### Findings
1. **Autosave base64 conversion** – Every autosave encodes full-resolution pixmaps to PNG strings, which is CPU and memory intensive for large collages, and the data remains in RAM until garbage collected.【F:src/widgets/collage.py†L130-L221】 _Update 2024-07: autosave payloads are now encoded via a background manager and cached per cell, keeping the UI thread responsive._
2. **Synchronous disk IO on UI thread** – Save/load flows invoke QFileDialog and image writes from the main thread, risking UI freezes for large exports or slow storage devices.【F:src/main.py†L444-L590】 _Update 2024-08: export writes now execute via a background worker with a modal progress dialog to keep the UI responsive._
3. **Performance tests lack thresholds** – `tests/performance/test_collage_layouts_perf.py` only asserts the timer ran, providing no regression guardrails or baseline storage, so perf regressions will go unnoticed.【F:tests/performance/test_collage_layouts_perf.py†L11-L32】

### Recommendations
- Cache autosave thumbnails or diffed states (e.g., hashing pixmaps, using incremental saves) and offload encoding to worker threads.
- Wrap heavy IO in `QRunnable`/`QThreadPool` tasks or asynchronous services while keeping the UI responsive.
- Establish performance budgets (e.g., `assert duration/loops < target_us`) and capture historical baselines in CI artifacts.

## 4. Testing & Quality Gates

### Findings
1. **UI flows untested** – Test coverage concentrates on utility classes; there are no unit or integration tests covering undo/redo, caption updates, or autosave restore paths within `MainWindow`/`CollageWidget` even though they contain critical logic.【F:tests/test_collage_layouts.py†L1-L24】【F:tests/test_image_processor.py†L1-L160】
2. **Path manipulation in tests** – Multiple tests mutate `sys.path` manually, making suite execution order-dependent and hiding import errors in packaged environments.【F:tests/test_collage_layouts.py†L1-L8】【F:tests/performance/test_collage_layouts_perf.py†L1-L8】
3. **Missing automated static analysis hooks** – No configuration files for ruff/black/isort/mypy were found, and CI docs do not mention linting gates, risking drift from style/security baselines.【F:README.md†L1-L120】

### Recommendations
- Add headless unit tests using Qt's `QSignalSpy` or by isolating logic into pure-Python classes; cover undo stack, caption toggles, and autosave serialization/deserialization.
- Replace manual `sys.path` hacking with proper package imports (e.g., editable install, `pytest.ini` with `pythonpath`), ensuring reproducible CI behavior.
- Document and enforce lint/type/test commands (ruff, black, mypy, pytest) and wire them into CI scripts.

## 5. UX/UI & Accessibility

### Findings
1. **Control density vs. affordance** – The control panel uses 30 px-high spin boxes/sliders, under the recommended 44 px touch target, challenging accessibility on high-DPI displays.【F:src/main.py†L128-L299】
2. **Limited accessible naming** – Only the collage grid is given an accessible name; action buttons, color pickers, and caption toggles lack `setAccessibleName`/`setToolTip`, reducing screen-reader navigability.【F:src/main.py†L212-L327】
3. **Styling bypasses theme tokens** – Some controls define inline style sheets inside the Python code rather than referencing shared tokens, causing duplication and making dark-mode support harder to maintain.【F:src/main.py†L130-L187】【F:ui/style.qss†L1-L62】

### Recommendations
- Increase interactive control heights to ≥36 px and align slider thumbs with WCAG target guidance; ensure consistent spacing tokens.
- Assign accessible names/roles to all actionable widgets and mirror them in tooltips/status text for assistive technologies.
- Centralize styling in `ui/style.qss` or token helpers instead of inline strings, enabling theme toggles and easier maintenance.

## Open Questions
- Missing: documented target frame rates or latency budgets for autosave/export flows.
- Missing: CI configuration to confirm lint/type/security tooling coverage.

