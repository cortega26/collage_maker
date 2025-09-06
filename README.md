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

### Running tests
```bash
pytest
```
