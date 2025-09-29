# Collage Maker

A desktop application for building image collages using Python and PySide6.

## Features
- Drag-and-drop image loading
- Grid based collage editor
- Export to PNG/JPEG/WebP

## Development
The project follows a modular structure under `src/`.  The global image
cache (`ImageCache`) was refactored for clarity and performance using an
`OrderedDict` based LRU implementation.

Recent refactoring moves layout definitions to dataclasses and reuses the
central LRU cache for image processing to reduce duplication and memory
usage.

### Requirements
See `requirements.txt` for the list of modern dependency versions.

### Running tests
```bash
pytest
```
- Meme-style captions (per image): top and bottom text with auto-fit, stroke, fill, uppercase toggle, and live preview. Included in exports.

### Captions

Each image cell supports two optional captions pinned to the top and bottom edges.

- Auto-fit: text wraps and scales between min/max font sizes to fit within safe margins.
- Legibility: stroke (outline) and fill colors with configurable width.
- Controls: Top/Bottom text areas, show/hide toggles, font family, min/max size, stroke width/color, fill color, UPPERCASE.
- Live Preview: typing updates the canvas after ~150ms debounce.
- Shortcuts: `T` focuses Top, `B` focuses Bottom, `Ctrl+Enter` applies.
- Export: captions are rasterized and included in PNG/JPEG.

If a caption cannot fit even at minimum size, the last line is ellipsized and the cell shows a tooltip: "Caption too long for image".

Example configuration for styles is provided in `examples/captions.json`.
