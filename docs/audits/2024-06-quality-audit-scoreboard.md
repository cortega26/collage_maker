# 2024-06 Quality Audit Scoreboard

| ID | Category | Finding | Status | Fix Reference | Notes |
| --- | --- | --- | --- | --- | --- |
| Q2 | Code Quality & Maintainability | Global logging uses static handlers without rotation, risking duplicate handlers and log bloat. | ✅ Resolved | This PR | Replaced `basicConfig` with idempotent rotating handler configuration. |
| Q1 | Code Quality & Maintainability | `MainWindow` control panel mixes UI creation and business logic, exceeding complexity targets. | ✅ Resolved | This PR | Extracted a reusable `ControlPanel` widget and bound signals from `MainWindow` to reduce controller complexity. |
| Q3 | Code Quality & Maintainability | `collage_app.py` diverges from PySide6 defaults and lacks shared validation. | ✅ Resolved | This PR | Legacy launcher now proxies to shared PySide6 window and validates CLI preload paths. |
| A1 | Architecture & Boundaries | UI tightly couples persistence and autosave flows. | ✅ Resolved | This PR | Added reusable session controller that mediates state/history outside the UI. |
| A2 | Architecture & Boundaries | Global mutable cache lacks dependency injection hooks. | ✅ Resolved | This PR | Added configurable factory + override context for the image cache. |
| A3 | Architecture & Boundaries | Autosave serialization is embedded in widget internals. | ✅ Resolved | This PR | Introduced dedicated autosave serializer module with dataclasses and widget integration. |
| P1 | Performance | Autosave performs base64 conversion on UI thread for full pixmaps. | ✅ Resolved | This PR | Added background autosave encoder that caches payloads per cell. |
| P2 | Performance | Save/load flows perform synchronous disk IO on UI thread. | ✅ Resolved | This PR | Export now streams via background worker with modal progress dialog. |
| P3 | Performance | Performance tests lack regression thresholds. | ✅ Resolved | This PR | Added baseline assertions and temp metrics capture for layout lookups. |
| T1 | Testing & Quality Gates | Critical UI flows lack automated coverage. | ✅ Resolved | This PR | Added headless MainWindow tests covering undo/redo and autosave snapshots. |
| T2 | Testing & Quality Gates | Tests manipulate `sys.path` directly. | ✅ Resolved | This PR | Added pytest configuration for pythonpath and removed per-test path mutations. |
| T3 | Testing & Quality Gates | Missing lint/type/static analysis configuration. | 🔧 Planned | — | Document and enforce lint/type/security tooling. |
| U1 | UX/UI & Accessibility | Control panel controls below recommended accessibility height. | 🔧 Planned | — | Revisit sizing to meet WCAG targets. |
| U2 | UX/UI & Accessibility | Accessible names/tooltips missing for many controls. | 🔧 Planned | — | Add accessible metadata for actionable widgets. |
| U3 | UX/UI & Accessibility | Inline styling bypasses shared theme tokens. | 🔧 Planned | — | Centralize styling within `style.qss`/token helpers. |

_Status legend: ✅ Resolved · 🔧 Planned · ⏳ In Progress · ⚠️ Blocked._
