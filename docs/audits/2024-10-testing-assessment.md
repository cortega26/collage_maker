# Test Suite & CI Assessment — October 2024

| Area | Observation | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| Coverage | No automated checks cover caption styling undo, autosave retry failures, or export worker error paths. | 【F:tests/test_mainwindow_session.py†L1-L160】【F:tests/test_autosave_manager.py†L1-L160】 | High-risk flows regress silently (QA-01, QA-02). | Add headless tests using `CollageSessionController` with mock adapters; simulate autosave write errors and assert `AutosaveError`. |
| Performance | Benchmarks exist but outputs unused; JSON metrics overwritten each run without diffing. | 【F:tests/performance/test_collage_layouts_perf.py†L10-L51】 | Regressions slip through; no alerting. | Store metrics as CI artefacts, compare vs baselines, fail on >10% regression. |
| Tooling | Lint/type/security commands documented but CI evidence missing. | 【F:pyproject.toml†L1-L160】【F:README.md†L1-L120】 | Style/security drift possible if CI misconfigured. | Publish CI config (link), enforce `ruff`, `black --check`, `isort --check-only`, `mypy`, `bandit`, `gitleaks`, `pip-audit`. |
| Flake Risk | GUI-centric tests rely on PySide6; absence of headless mocks encourages reliance on manual QA. | 【F:tests/test_mainwindow_session.py†L1-L160】 | Increased flake potential on CI environments lacking display server. | Expand pure-python controller tests and mark GUI E2E as optional smoke gated by xvfb. |

## Action Plan
1. Implement regression tests for QA-01 and QA-02 alongside fixes.
2. Add coverage reporting to CI; target ≥80% overall, ≥90% for modules touched by fixes.
3. Integrate secret scanning (`gitleaks`) and vulnerability audit (`pip-audit`) into default workflow.
