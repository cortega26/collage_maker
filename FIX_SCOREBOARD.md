| ID | Area | Finding | Severity | Status | Owner | Notes |
|----|-------|---------|----------|--------|-------|-------|
| F-01 | UI | Import caption panel dependencies (`src/main.py:13`) | High | Fixed | — | Added QPlainTextEdit, QFontComboBox, and QColorDialog imports; caption tools no longer raise `NameError`. |
| F-02 | UI | Mount caption panel into layout (`src/main.py:86`) | High | Fixed | — | Caption controls panel is now instantiated once and inserted beneath the toolbar. |
| F-03 | UI | Fix Add Images import when run as script (`src/main.py:26`) | High | Fixed | — | ImageOptimizer now imported via the top-level fallback block; `_add_images` reuses it safely in both entry modes. |
| F-04 | UI | Preserve cell state during grid resize (`src/widgets/collage.py:252`) | High | Fixed | — | `update_grid` now snapshots cells, rehydrates them after resize, and keeps merges where possible. |
| F-05 | Imaging | Store originals separately & key cache by size (`src/widgets/cell.py:99`, `src/widgets/cell.py:460`) | Critical | Fixed | — | Cells now keep full-res pixmaps and cache entries include target size. |
| F-06 | UI | Ensure temp autosave directory exists (`ui/collage_canvas.py:59`) | Medium | Open | — | Prevent silent autosave failures. |
| F-07 | UI | Re-layout after spacing changes (`ui/collage_canvas.py:359`) | Medium | Open | — | Make spacing control functional. |
| F-08 | UI | Route drag/drop through validated loader (`ui/image_label.py:56`) | Medium | Open | — | Apply shared validation & resizing rules. |
| F-09 | Config | Align default spacing with 8 px requirement (`src/config.py:10`) | Medium | Open | — | Match product spec. |
| B-01 | Backend | Validate output paths before saving (`utils/image_processor.py:144`) | High | Open | — | Guard against invalid destinations. |
| B-02 | Backend | Honor batch worker return codes (`utils/image_processor.py:263`) | High | Open | — | Surface failed conversions. |
| B-03 | Ops | Serialize full collage state for autosave (`src/main.py:576`) | High | Open | — | Make recovery meaningful. |
| QA-01 | Tests | Re-run `pytest -q` once interpreter access is restored | Medium | Blocked | — | Environment missing `python`. |
