# Collage Maker Quality Audit (October 2024)

## Executive Summary
- **Overall posture:** Core data structures remain solid, but the PySide6 shell centralises critical workflows inside `MainWindow`, reintroducing tight UI/business coupling and blocking I/O that risks freezes during core flows.【F:src/main.py†L201-L846】【F:src/managers/autosave.py†L52-L94】
- **Critical regressions:** Autosave and export routines now perform synchronous disk work (with sleeps) on the UI thread, producing S0 responsiveness defects. Undo coverage for caption styling was never wired, so keyboard undo fails after text styling changes.【F:src/managers/autosave.py†L61-L94】【F:src/main.py†L234-L268】
- **Opportunities:** Reinstate strict path validation before loading/saving media, split orchestration responsibilities into injectable services, and document/automate Web Vitals budgets alongside regression tests for undo/autosave.

## Audit Method
1. **Business flows reviewed:** (a) add images → adjust captions → save export, (b) reopen autosave after crash, (c) merge/split cells with undo/redo.
2. **Tooling:** static inspection of `src/`, `utils/`, `ui/`, and `tests/` (Python 3.11); runtime smoke via `pytest -q` (green, 27 passed / 3 skipped).
3. **Quality budgets introduced:**
   - **Complexity:** functions >80 LOC require decomposition; target ≤10 cyclomatic complexity for interaction handlers.
   - **Responsiveness:** UI-thread work must stay under 16 ms budget per event; autosave/export I/O must run off the GUI thread.
   - **Undo reliability:** all visible toolbar actions must capture undo snapshots with ≥1 regression test per action.
   - **Accessibility:** interactive controls ≥36 px tall with accessible name + state, colour contrast ≥4.5:1, keyboard order sequential.
   - **Performance:** autosave completion ≤150 ms, export UI-blocking ≤250 ms, layout utilities ≤5 µs per lookup.
   - **Testing:** regression coverage for autosave failure paths and caption undo (mocks acceptable); performance tests must emit metrics artefacts.

## 1. Code Maintainability & Architecture

### Findings
1. **Monolithic `MainWindow` orchestration (S1, Eng Lead)** – The class spans ~850 LOC, constructing widgets, file dialogs, autosave, undo, image optimisation, and export flows directly. This violates separation of concerns and complicates headless testing or reuse.【F:src/main.py†L201-L846】  
   _Recommendation:_ Extract presenters/services (`ExportService`, `AutosaveController`, `CaptionStyler`) injected into a slim window; expose them via dependency container for tests.
2. **Caption styling bypasses undo controller (S1, Front-end Lead)** – `_pick_color` and `_apply_captions_now` mutate selected cells without calling `_capture_for_undo` or refreshing baselines, so Ctrl+Z leaves styling changes intact.【F:src/main.py†L234-L268】
   _Recommendation:_ Capture undo snapshot before scheduling caption updates, coalesce timer flush into controller, and record baseline once updates succeed.
   _Status update (Nov 2024): Caption styling changes now capture undo snapshots for timer-driven updates and color picks, with regression tests covering undo/redo expectations._【F:src/main.py†L237-L293】【F:tests/test_mainwindow_session.py†L236-L326】
3. **Template handler silences errors (S2, Product Owner)** – `_apply_template` swallows all exceptions, leaving stale grids if template text is malformed, with no feedback for the user or logs.【F:src/main.py†L349-L356】  
   _Recommendation:_ Validate template strings (`r"^\d+x\d+$"`), show toast/dialog on invalid input, and keep combo in sync.
4. **Cache abstraction still effectively global (S2, Back-end Lead)** – Although `src/cache.py` offers configuration helpers, most callers pull `image_cache` proxy directly, making instrumentation and per-widget overrides awkward.【F:src/cache.py†L1-L154】  
   _Recommendation:_ Pass cache instances into widgets/controllers explicitly, provide context manager usage guidelines, and add tracing hooks.

## 2. Performance & Reliability

### Findings
1. **Autosave runs entirely on UI thread (S0, Eng Lead)** – `AutosaveManager.perform_autosave` writes JSON synchronously and uses `time.sleep` for retries inside the GUI thread, freezing the window for 100–700 ms and compounding under IO stalls.【F:src/managers/autosave.py†L61-L94】
   _Recommendation:_ Move serialization + retries into a `Worker`, replace sleeps with `QTimer.singleShot`, and emit progress telemetry.
   _Status update (Nov 2024): Autosave now snapshots state on the UI thread but streams disk writes via a background `Worker` with retry scheduling driven by `QTimer.singleShot`, eliminating UI blocking and exposing a `wait_for_idle` hook for deterministic tests._【F:src/managers/autosave.py†L64-L228】【F:tests/test_autosave_manager.py†L1-L86】
2. **Original export recomposition is synchronous (S1, Eng Lead)** – `_compose_original_image` builds a giant `QImage` from every original pixmap before dispatching the worker, causing multi-hundred MB allocations and long blocking paints for high-res collages.【F:src/main.py†L779-L817】  
   _Recommendation:_ Stream originals to disk (tile writer) within worker threads or lazily compose per-row to cap memory.
3. **Add Images path validation skipped (S1, Back-end Lead)** – `_add_images` trusts dialog return values, never invoking `utils.validation.validate_image_path`, so crafted strings (`file://` or unsupported suffixes) reach `QImageReader`, which can hang UI while probing remote paths.【F:src/main.py†L726-L762】【F:utils/validation.py†L16-L45】
   _Recommendation:_ Validate each selection before read, reject unsupported schemes, and surface actionable errors.
   _Status update (Nov 2024): Main window now validates selections via `_validate_selected_images`, reports rejected paths to the user, and prevents URL schemes from reaching `QImageReader`._【F:src/main.py†L748-L833】【F:tests/test_mainwindow_session.py†L121-L168】
4. **Save path validation absent (S1, Back-end Lead)** – `_select_save_path` auto-appends extensions but allows directories that do not exist or wrong suffixes, deferring failures to the worker and producing generic IOErrors.【F:src/main.py†L624-L641】【F:utils/validation.py†L47-L70】  
   _Recommendation:_ Validate output path immediately, prompt to create directories, and keep history of last-good location.

## 3. UX/UI & Accessibility

### Findings
1. **Colour pickers lack state narration (S1, Front-end Lead)** – Caption stroke/fill buttons expose generic labels without reflecting the currently chosen colour, and nothing updates accessible descriptions when colours change, leaving screen-reader users guessing.【F:src/widgets/control_panel.py†L166-L207】  
   _Recommendation:_ Announce ARGB values via `setAccessibleDescription`, emit status-bar text, and keep focus traversal grouped.
2. **Caption toggle group loses focus context (S2, Front-end Lead)** – Focus order jumps from `Show Top` to font combo to uppercase toggle, skipping the slider/spin pair, violating logical grouping.【F:src/widgets/control_panel.py†L166-L213】  
   _Recommendation:_ Introduce `QGroupBox` or manual focus proxies, ensuring sequential tab order and descriptive grouping labels.
3. **Dialogs rely on default titles (S2, Product Owner)** – Save/export progress dialog removes cancel button but keeps empty label text, giving assistive tech no indication of status beyond title.【F:src/main.py†L642-L691】  
   _Recommendation:_ Set descriptive text, progress range updates, and accessible names to communicate busy state.

## 4. Testing & Quality Gates

### Findings
1. **Undo/caption regression tests missing (S2, QA Lead)** – `tests/test_mainwindow_session.py` covers undo stack service but not the caption timer/colour flows, allowing regressions like QA-02 to ship unnoticed.【F:tests/test_mainwindow_session.py†L1-L160】  
   _Recommendation:_ Add controller-level tests exercising caption updates with spy adapters; verify undo baseline updates.
2. **Autosave failure path untested (S2, QA Lead)** – No tests simulate write failures or ensure `AutosaveError` surfaces after retries, and metrics counters are unasserted.【F:src/managers/autosave.py†L61-L94】【F:tests/test_autosave_manager.py†L1-L160】  
   _Recommendation:_ Mock filesystem errors, assert retry timing (without real sleep once refactored), and verify metrics increments.
3. **Performance tests lack artefact guardrails (S2, QA Lead)** – Benchmarks record JSON results but there is no CI hook consuming them or threshold diffing; budgets risk regression without alerts.【F:tests/performance/test_collage_layouts_perf.py†L10-L51】  
   _Recommendation:_ Persist metrics via CI artefacts, diff against baselines, and alert when drift exceeds 10%.

## 5. Web Vitals & Responsiveness Summary
- **Budgets:** LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1 for PySide6 launch screens; autosave must avoid blocking >100 ms on UI thread.
- **Blocking scripts:** Autosave JSON writes (≈600 ms worst-case) and original recomposition (dependent on input) currently breach budgets.【F:src/managers/autosave.py†L61-L94】【F:src/main.py†L779-L817】
- **Deferred measurements:** No Lighthouse or frame-timing traces were provided; schedule capture once autosave/export are off-thread.

## Open Questions / Missing Data
- Missing: recorded autosave/export durations under realistic loads.
- Missing: accessibility audit logs (axe or keyboard walkthrough outputs) to confirm announced names after fixes.
- Missing: CI configuration proving lint/type/security gates execution.

## Recommended Next Steps
1. Ship backlog items QA-01..QA-04 as blockers for upcoming release; they directly affect core flows.
2. Schedule refactor of `MainWindow` into injectable services to unlock reliable testing and enable background workers.
3. Establish automated performance + accessibility checks (pre-submit) once synchronous bottlenecks are removed.
