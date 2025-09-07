from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional, Union
from dataclasses import dataclass
import logging
from PIL import Image, UnidentifiedImageError
import hashlib
from concurrent.futures import ThreadPoolExecutor

from src.cache import ImageCache
from .image_operations import apply_operations
from .validation import validate_image_path

@dataclass(slots=True)
class ImageInfo:
    """
    Contains information about an image.
    
    Attributes:
        format (str): Image format (e.g., JPEG, PNG)
        mode (str): Color mode
        size (Tuple[int, int]): Image dimensions
        dpi (Optional[Tuple[float, float]]): DPI information
        color_space (str): Color space information
        exif (Optional[Dict]): EXIF metadata
    """
    format: str
    mode: str
    size: Tuple[int, int]
    dpi: Optional[Tuple[float, float]]
    color_space: str
    exif: Optional[Dict]

class ImageProcessingError(Exception):
    """Custom exception for image processing errors."""
    pass

class ImageProcessor:
    """Handles image processing operations with caching and validation."""
    
    VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
    MAX_IMAGE_SIZE = 10000  # Maximum dimension in pixels
    QUALITY = 95  # Default JPEG quality
    
    def __init__(self, cache: Optional[ImageCache] = None):
        """Initialize the image processor."""
        self._cache: ImageCache = cache or ImageCache()
        self._thread_pool = ThreadPoolExecutor(max_workers=4)
        
    @staticmethod
    def is_valid_image(file_path: Union[str, Path]) -> bool:
        """
        Check if the given file is a valid image.
        
        Args:
            file_path: Path to the image file
            
        Returns:
            bool: True if the file is a valid image
        """
        try:
            path = Path(file_path)
            if not path.is_file():
                return False
                
            if path.suffix.lower() not in ImageProcessor.VALID_EXTENSIONS:
                return False

            # Validate image data
            with Image.open(path) as img:
                img.verify()

            return True
        except (UnidentifiedImageError, OSError) as e:
            logging.warning(f"Invalid image file {file_path}: {e}")
            return False
            
    def process_image(
        self,
        image_path: Union[str, Path],
        operations: List[Dict[str, Any]],
        output_path: Optional[Union[str, Path]] = None
    ) -> Image.Image:
        """
        Process an image with a series of operations.
        
        Args:
            image_path: Path to the input image
            operations: List of operations to apply
            output_path: Optional path to save the result
            
        Returns:
            Image.Image: Processed image
            
        Raises:
            ImageProcessingError: If processing fails
        """
        try:
            # Validate input
            safe_path = validate_image_path(image_path, self.VALID_EXTENSIONS)

            # Generate cache key
            cache_key = self._generate_cache_key(safe_path, operations)
            
            # Check cache
            cached_result, _ = self._cache.get(cache_key)
            if cached_result is not None:
                return cached_result
                
            # Process image
            with Image.open(safe_path) as img:
                result = self._apply_operations(img, operations)
                
                # Cache result
                self._cache.put(cache_key, result, {})
                
                # Save if output path provided
                if output_path:
                    self._save_image(result, output_path)
                    
                return result
                
        except Exception as e:
            logging.error(f"Error processing image {image_path}: {e}")
            raise ImageProcessingError(f"Failed to process image: {e}")
            
    def _generate_cache_key(self, image_path: Union[str, Path], operations: List[Dict[str, Any]]) -> str:
        """Generate a unique cache key for the image and operations."""
        key_data = f"{image_path}:{str(operations)}"
        return hashlib.md5(key_data.encode()).hexdigest()
        
    def _apply_operations(self, image: Image.Image, operations: List[Dict[str, Any]]) -> Image.Image:
        """Apply a series of operations to an image."""
        return apply_operations(image, operations)
        
    def _save_image(self, image: Image.Image, output_path: Union[str, Path]) -> None:
        """Save an image with optimal settings."""
        path = Path(output_path)
        format = path.suffix[1:].upper()
        
        save_params = {
            'format': format,
            'quality': self.QUALITY if format in ['JPEG', 'WEBP'] else None,
            'optimize': True
        }
        
        image.save(str(path), **save_params)
        
    @staticmethod
    def get_image_info(image_path: Union[str, Path]) -> ImageInfo:
        """
        Get detailed information about an image.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            ImageInfo: Information about the image
            
        Raises:
            ImageProcessingError: If information cannot be retrieved
        """
        try:
            with Image.open(image_path) as img:
                return ImageInfo(
                    format=img.format,
                    mode=img.mode,
                    size=img.size,
                    dpi=img.info.get('dpi'),
                    color_space=img.mode,
                    exif=img._getexif() if hasattr(img, '_getexif') else None
                )
        except Exception as e:
            raise ImageProcessingError(f"Failed to get image info: {e}")
            
    def process_batch(
        self,
        image_paths: List[Union[str, Path]],
        operations: List[Dict[str, Any]],
        output_dir: Union[str, Path]
    ) -> Dict[str, bool]:
        """
        Process multiple images in parallel.
        
        Args:
            image_paths: List of paths to input images
            operations: List of operations to apply
            output_dir: Directory to save processed images
            
        Returns:
            Dict[str, bool]: Dictionary mapping input paths to success status
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {}
        futures = []

        for path in image_paths:
            try:
                input_path = validate_image_path(path, self.VALID_EXTENSIONS)
            except ValueError as exc:
                logging.error(f"Invalid image path {path}: {exc}")
                results[str(path)] = False
                continue

            output_path = output_dir / input_path.name
            future = self._thread_pool.submit(
                self.process_image,
                input_path,
                operations,
                output_path
            )
            futures.append((path, future))
            
        for path, future in futures:
            try:
                future.result()
                results[str(path)] = True
            except Exception as e:
                logging.error(f"Failed to process {path}: {e}")
                results[str(path)] = False
                
        return results
