# config.py
"""
Application configuration constants for Collage Maker
"""

# Grid defaults
DEFAULT_ROWS = 2
DEFAULT_COLUMNS = 2
DEFAULT_CELL_SIZE = 260
DEFAULT_SPACING = 2

# Cache settings
MAX_CACHE_SIZE = 50
CACHE_CLEANUP_THRESHOLD = 0.8  # Cleanup when cache reaches 80% of max size

# Supported image formats
SUPPORTED_IMAGE_FORMATS = ['png', 'jpg', 'jpeg', 'bmp', 'webp', 'gif', 'tiff']

# Image dimension limits
MAX_IMAGE_DIMENSION = 4000       # Maximum width/height for loaded images
MAX_DISPLAY_DIMENSION = 2000     # Maximum dimension for display optimization

# Autosave settings
AUTOSAVE_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes in milliseconds
AUTOSAVE_PATH = "autosave"
MAX_AUTOSAVE_FILES = 5
AUTOSAVE_TIMESTAMP_FORMAT = "yyyyMMdd_HHmmss"

# Performance monitor settings
MEMORY_THRESHOLD_BYTES = 500 << 20  # 500 MB
MEMORY_CLEANUP_INTERVAL_SECS = 300  # 5 minutes in seconds

# Error recovery settings
ERROR_THRESHOLD = 5
ERROR_WINDOW_SECONDS = 300  # 5 minutes window

# Save dialog defaults
SAVE_SHORTCUT = "Ctrl+S"
SAVE_ORIGINAL_SHORTCUT = "Ctrl+Shift+S"

# Save dialog options
QUALITY_MIN = 1
QUALITY_MAX = 100
QUALITY_DEFAULT = 95
RESOLUTION_MULTIPLIERS = [1, 2, 4]
