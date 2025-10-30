# 2024-10 Quality Audit Scoreboard

| ID | Severity | Area | Finding | Owner | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| QA-01 | S0 | Performance | Autosave writes + sleeps on UI thread freeze the window during retries.【F:src/managers/autosave.py†L61-L94】 | Engineering Lead | ⚠️ Open | Move autosave to background worker and replace blocking sleeps. |
| QA-02 | S1 | UX/Undo | Caption styling bypasses undo history, so Ctrl+Z does nothing after styling changes.【F:src/main.py†L234-L268】 | Front-end Lead | ⚠️ Open | Capture undo snapshots before styling timer fires and refresh baseline post-apply. |
| QA-03 | S1 | Security & IO | `Add Images` accepts unvalidated paths/schemes, risking hangs on invalid inputs.【F:src/main.py†L748-L833】 | Back-end Lead | ✅ Done | Validate each chosen path and surface actionable errors before loading.【F:src/main.py†L748-L833】 |
| QA-04 | S1 | Security & IO | Save dialog allows invalid directories/extensions, deferring failures to export worker.【F:src/main.py†L624-L641】 | Back-end Lead | ⚠️ Open | Validate output path and prompt user before running worker. |
| QA-05 | S1 | Maintainability | `MainWindow` still orchestrates autosave/export/history directly in ~850 LOC.【F:src/main.py†L201-L846】 | Engineering Lead | ⚠️ Open | Factor into services/presenters with dependency injection seams. |
| QA-06 | S1 | Performance | Original export recomposes massive `QImage` synchronously before worker dispatch.【F:src/main.py†L779-L817】 | Engineering Lead | ⚠️ Open | Stream/tile original export work off the UI thread. |
| QA-07 | S1 | Accessibility | Caption colour controls do not announce current selection or maintain logical focus grouping.【F:src/widgets/control_panel.py†L166-L213】 | Front-end Lead | ⚠️ Open | Add accessible descriptions and reorder focus chain. |
| QA-08 | S2 | Architecture | Cache proxy still hides lifecycle; instrumentation/mocking is awkward.【F:src/cache.py†L1-L154】 | Back-end Lead | ⚠️ Open | Pass cache dependencies explicitly and expose instrumentation hooks. |
| QA-09 | S2 | Testing | Undo/autosave failure paths uncovered by automated tests.【F:tests/test_mainwindow_session.py†L1-L160】【F:tests/test_autosave_manager.py†L1-L160】 | QA Lead | ⚠️ Open | Add regression tests for caption undo + autosave retries. |
| QA-10 | S2 | UX | Template parsing swallows errors leaving stale UI with no feedback.【F:src/main.py†L349-L356】 | Product Owner | ⚠️ Open | Validate template strings and surface friendly error state. |

_Status legend: ✅ Done · 🔧 In Progress · ⚠️ Open · ⏳ Blocked._
