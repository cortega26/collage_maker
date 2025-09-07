from dataclasses import dataclass, field
from typing import List, Dict
import logging
from pathlib import Path
import json
from functools import lru_cache


@dataclass(slots=True)
class CollageLayout:
    """Represents a collage layout configuration."""

    name: str
    grid: List[List[int]]
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validate_grid()

    def _validate_grid(self) -> None:
        """
        Validate the grid structure.
        
        Raises:
            ValueError: If the grid structure is invalid
        """
        if not isinstance(self.grid, list) or not self.grid:
            raise ValueError("Grid must be a non-empty 2D list")
            
        if not all(isinstance(row, list) for row in self.grid):
            raise ValueError("Grid must contain only lists")
            
        if not all(all(isinstance(cell, int) and cell >= 0 for cell in row) for row in self.grid):
            raise ValueError("Grid cells must be non-negative integers")
            
        row_lengths = {len(row) for row in self.grid}
        if len(row_lengths) > 1:
            raise ValueError("All rows must have the same length")

    @property
    def rows(self) -> int:
        """Get the number of rows in the layout."""
        return len(self.grid)
        
    @property
    def cols(self) -> int:
        """Get the number of columns in the layout."""
        return len(self.grid[0]) if self.grid else 0

    def get_cell_dimensions(self, canvas_width: int, canvas_height: int, spacing: int = 2) -> List[Dict[str, int]]:
        """
        Calculate the dimensions of each cell in the layout.
        
        Args:
            canvas_width (int): Width of the canvas
            canvas_height (int): Height of the canvas
            spacing (int): Spacing between cells
            
        Returns:
            List[Dict[str, int]]: List of cell dimensions
        """
        # Calculate available space after spacing
        total_spacing_width = spacing * (self.cols - 1)
        total_spacing_height = spacing * (self.rows - 1)
        
        available_width = max(1, canvas_width - total_spacing_width)
        available_height = max(1, canvas_height - total_spacing_height)
        
        # Calculate base cell dimensions
        cell_width = available_width // self.cols
        cell_height = available_height // self.rows
        
        dimensions = []
        
        # Calculate dimensions for each cell
        for i, row in enumerate(self.grid):
            for j, cell in enumerate(row):
                if cell > 0:
                    # Calculate position with spacing
                    x = j * (cell_width + spacing)
                    y = i * (cell_height + spacing)
                    
                    # Calculate size considering merged cells
                    width = cell_width * cell + spacing * (cell - 1)
                    height = cell_height * cell + spacing * (cell - 1)
                    
                    dimensions.append({
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height
                    })
        
        return dimensions

    def to_dict(self) -> Dict:
        """Convert the layout to a dictionary representation."""
        return {
            "name": self.name,
            "grid": self.grid,
            "description": self.description,
            "tags": self.tags
        }
        
    @classmethod
    def from_dict(cls, data: Dict) -> 'CollageLayout':
        """Create a layout from a dictionary representation."""
        required_keys = {"name", "grid"}
        if not all(key in data for key in required_keys):
            raise ValueError(f"Missing required keys: {required_keys - data.keys()}")
            
        return cls(
            name=data["name"],
            grid=data["grid"],
            description=data.get("description", ""),
            tags=data.get("tags", [])
        )

class CollageLayouts:
    """Manages collage layout configurations."""
    
    # Default layouts
    LAYOUTS: Dict[str, CollageLayout] = {
        "2x2": CollageLayout(
            "2x2",
            [[1, 1], [1, 1]],
            "Basic 2x2 grid layout",
            ["basic", "grid"]
        ),
        "3x3": CollageLayout(
            "3x3",
            [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
            "Basic 3x3 grid layout",
            ["basic", "grid"]
        ),
        "2x3": CollageLayout(
            "2x3",
            [[1, 1], [1, 1], [1, 1]],
            "Basic 2x3 grid layout",
            ["basic", "grid"]
        ),
        "3x2": CollageLayout(
            "3x2",
            [[1, 1, 1], [1, 1, 1]],
            "Basic 3x2 grid layout",
            ["basic", "grid"]
        ),
        "4x2": CollageLayout(
            "4x2",
            [[1, 1, 1, 1], [1, 1, 1, 1]],
            "Basic 4x2 grid layout",
            ["basic", "grid"]
        ),
        "2x4": CollageLayout(
            "2x4",
            [[1, 1], [1, 1], [1, 1], [1, 1]],
            "Basic 2x4 grid layout",
            ["basic", "grid"]
        ),
        "4x3": CollageLayout(
            "4x3",
            [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]],
            "Basic 4x3 grid layout",
            ["basic", "grid"]
        ),
        "3x4": CollageLayout(
            "3x4",
            [[1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1]],
            "Basic 3x4 grid layout",
            ["basic", "grid"]
        ),
        "4x4": CollageLayout(
            "4x4",
            [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]],
            "Basic 4x4 grid layout",
            ["basic", "grid"]
        ),
    }
    
    @classmethod
    def get_layout(cls, name: str) -> CollageLayout:
        """Get a layout by name."""
        try:
            return cls.LAYOUTS[name]
        except KeyError:
            logging.error(f"Layout '{name}' not found")
            raise ValueError(f"Layout '{name}' not found")
            
    @classmethod
    @lru_cache(maxsize=None)
    def get_layout_names(cls) -> List[str]:
        """Get a list of all available layout names.

        Big-O:
            Before caching: ``O(n log n)`` for sorting ``n`` layouts.
            After caching: ``O(n log n)`` once; ``O(1)`` on repeated calls
            until layouts change.
        """
        return sorted(cls.LAYOUTS.keys())

    @classmethod
    @lru_cache(maxsize=None)
    def get_layouts_by_tag(cls, tag: str) -> List[CollageLayout]:
        """Get layouts filtered by tag.

        Big-O:
            Before caching: ``O(n)`` per call to scan ``n`` layouts.
            After caching: ``O(n)`` for the first call of a tag, ``O(1)`` for
            subsequent requests for the same tag.
        """
        return [
            layout for layout in cls.LAYOUTS.values()
            if tag in layout.tags
        ]

    @classmethod
    def _invalidate_caches(cls) -> None:
        """Clear cached layout lookups."""
        cls.get_layout_names.cache_clear()
        cls.get_layouts_by_tag.cache_clear()
        
    @classmethod
    def add_custom_layout(cls, layout: CollageLayout) -> None:
        """Add a custom layout."""
        if layout.name in cls.LAYOUTS:
            raise ValueError(f"Layout '{layout.name}' already exists")

        cls.LAYOUTS[layout.name] = layout
        logging.info(f"Added new layout: {layout.name}")
        cls._invalidate_caches()
        
    @classmethod
    def remove_layout(cls, name: str) -> None:
        """Remove a layout by name."""
        try:
            del cls.LAYOUTS[name]
            logging.info(f"Removed layout: {name}")
        except KeyError:
            raise ValueError(f"Layout '{name}' not found")
        else:
            cls._invalidate_caches()
            
    @classmethod
    def save_layouts(cls, file_path: str) -> None:
        """Save all layouts to a JSON file."""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            layouts_data = {
                name: layout.to_dict()
                for name, layout in cls.LAYOUTS.items()
            }
            
            with path.open('w', encoding='utf-8') as f:
                json.dump(layouts_data, f, indent=2)
                
            logging.info(f"Saved layouts to {file_path}")
        except Exception as e:
            logging.error(f"Failed to save layouts: {e}")
            raise
            
    @classmethod
    def load_layouts(cls, file_path: str) -> None:
        """Load layouts from a JSON file."""
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"Layout file not found: {file_path}")
                
            with path.open('r', encoding='utf-8') as f:
                layouts_data = json.load(f)

            for name, layout_data in layouts_data.items():
                cls.LAYOUTS[name] = CollageLayout.from_dict(layout_data)

            logging.info(f"Loaded layouts from {file_path}")
            cls._invalidate_caches()
        except Exception as e:
            logging.error(f"Failed to load layouts: {e}")
            raise
