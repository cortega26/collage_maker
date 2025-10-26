# Collage Maker

A desktop application for building image collages using Python and PySide6.

## Highlights
- Drag-and-drop images from your file manager (multi-file supported).
- Grid-based editor with quick templates (2x2, 3x3, 2x3, 3x2, 4x4).
- Responsive tiles adapt to window aspect ratio (no wasted space).
- Per-image filters and adjustments (right-click a cell).
- Per-image meme-style captions (top/bottom) with auto-fit, stroke, fill.
- DPI-aware export to PNG/JPEG/WebP (crisp output; safe size clamping).
- Accessible UI: visible focus, keyboard support, high-contrast tokens.

## Install
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell
pip install -r requirements.txt
```

## Run
From the project root:
```bash
python main.py
```
Alternatively:
```bash
python -m src.main
# or
python src/main.py
```

Theme (optional):
```bash
$env:COLLAGE_THEME='dark'   # PowerShell
python main.py
```

## Usage
- Add images
  - Drag-and-drop files directly onto the collage grid, or use the “Add Images…” button. Empty cells fill in reading order.
- Select images
  - Ctrl+Click toggles selection. Delete clears selected.
- Templates
  - Use the “Templates” dropdown to quickly set rows/cols.
- Per-image filters/adjustments
  - Right-click a cell → Filters / Adjustments.
- Per-image captions (meme-style)
  - Right-click a cell → Captions → Edit Top Caption… / Edit Bottom Caption…
  - Toggle visibility: Captions → Show Top / Show Bottom.
  - Captions auto-fit within safe margins; stroke and fill colors are configurable at the cell level.
- Export
  - Click “Save Collage”. Choose format, quality, and resolution multiplier. Exports include captions and are clamped to a safe max dimension.

## Captions
Each image cell supports two optional captions pinned to the top and bottom edges.

- Auto-fit: text wraps and scales between min/max font sizes to fit within safe margins.
- Legibility: stroke (outline) and fill colors with configurable width; drawn via QPainterPath (stroke then fill).
- Per-image control: edit captions and show/hide via a cell’s context menu.
- Export: captions are rasterized and included in PNG/JPEG.
- Overflow: if a caption cannot fit even at minimum size, the last line is ellipsized and the cell shows a tooltip: _“Caption too long for image”_.

An example style config is provided in `examples/captions.json`.

## Keyboard
- Ctrl+O: Add Images
- Ctrl+Shift+C: Clear All
- Delete: Clear selected cell(s)
- Ctrl+S: Save Collage
- Ctrl+Shift+S: Save Original Collage

## Troubleshooting
- On Windows, save dialogs default to your Pictures folder. The app uses a non-native dialog to avoid localized known-folder path issues.
- If spin boxes or combo popups show low contrast text, the app overlays token styles; per-widget overrides are applied for common platform quirks.

## Development
Code lives under `src/`.

- Design system: `src/style_tokens.py` provides color/typography/spacing tokens and generates QSS. Set `COLLAGE_THEME=dark` to toggle.
- Image pipeline: `utils/image_processor.py` applies EXIF transpose, optional decoder downscale, and format-aware saves (JPEG progressive / WebP method / PNG optimize).
- Performance: `src/cache.py` is a thread-safe LRU. `src/optimizer.py` uses positional args for `QImage.scaled()` for broad PySide6 compatibility.

### Tests
```bash
pytest -q
```

### Code quality checks
The project ships with shared configuration in `pyproject.toml` for linting, formatting, typing, and security scanning. Run the
following commands from the repository root before sending changes for review:

| Tool | Command | Description |
| --- | --- | --- |
| Ruff | `ruff check .` | Fast linting (includes import sorting). |
| Black | `black --check .` | Verifies formatting using the shared profile. |
| isort | `isort --check-only .` | Ensures import order matches project conventions. |
| mypy | `mypy .` | Static type checks with PySide6 shims ignored. |
| bandit | `bandit -ll -r .` | Security lint focusing on high/medium severity issues. |
| gitleaks | `gitleaks detect --no-banner` | Scans for accidentally committed secrets. |
| pip-audit | `pip-audit` | Reports known vulnerabilities in Python dependencies. |

> Note: Network access may be required for `pip-audit`.
