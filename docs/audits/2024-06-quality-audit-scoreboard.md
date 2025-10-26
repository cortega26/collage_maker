# 2024-06 Quality Audit Scoreboard

| ID | Category | Finding | Status | Fix Reference | Notes |
| --- | --- | --- | --- | --- | --- |
| Q2 | Code Quality & Maintainability | Global logging uses static handlers without rotation, risking duplicate handlers and log bloat. | ✅ Resolved | This PR | Replaced `basicConfig` with idempotent rotating handler configuration. |
| Q1 | Code Quality & Maintainability | `MainWindow` control panel mixes UI creation and business logic, exceeding complexity targets. | ✅ Resolved | This PR | Extracted a reusable `ControlPanel` widget and bound signals from `MainWindow` to reduce controller complexity. |
| Q3 | Code Quality & Maintainability | `collage_app.py` diverges from PySide6 defaults and lacks shared validation. | 🔧 Planned | — | Evaluate deprecation vs. refactor toward shared widgets. |
| A1 | Architecture & Boundaries | UI tightly couples persistence and autosave flows. | 🔧 Planned | — | Introduce controller/service layer for headless automation. |
| A2 | Architecture & Boundaries | Global mutable cache lacks dependency injection hooks. | 🔧 Planned | — | Consider factory or DI container for cache strategy swaps. |
| A3 | Architecture & Boundaries | Autosave serialization is embedded in widget internals. | 🔧 Planned | — | Move toward serializer operating on data model. |
| P1 | Performance | Autosave performs base64 conversion on UI thread for full pixmaps. | 🔧 Planned | — | Evaluate worker-based encoding or incremental saves. |
| P2 | Performance | Save/load flows perform synchronous disk IO on UI thread. | 🔧 Planned | — | Offload heavy IO to worker threads. |
| P3 | Performance | Performance tests lack regression thresholds. | 🔧 Planned | — | Add baseline assertions and store metrics. |
| T1 | Testing & Quality Gates | Critical UI flows lack automated coverage. | 🔧 Planned | — | Add headless tests for undo/redo and autosave flows. |
| T2 | Testing & Quality Gates | Tests manipulate `sys.path` directly. | 🔧 Planned | — | Replace with package imports/pytest configuration. |
| T3 | Testing & Quality Gates | Missing lint/type/static analysis configuration. | 🔧 Planned | — | Document and enforce lint/type/security tooling. |
| U1 | UX/UI & Accessibility | Control panel controls below recommended accessibility height. | 🔧 Planned | — | Revisit sizing to meet WCAG targets. |
| U2 | UX/UI & Accessibility | Accessible names/tooltips missing for many controls. | 🔧 Planned | — | Add accessible metadata for actionable widgets. |
| U3 | UX/UI & Accessibility | Inline styling bypasses shared theme tokens. | 🔧 Planned | — | Centralize styling within `style.qss`/token helpers. |

_Status legend: ✅ Resolved · 🔧 Planned · ⏳ In Progress · ⚠️ Blocked._
