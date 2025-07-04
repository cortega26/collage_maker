from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional, Union
from dataclasses import dataclass
import logging
import imghdr
from PIL import Image, ImageEnhance, ImageFilter, UnidentifiedImageError
import hashlib
import io
import threading
from concurrent.futures import ThreadPoolExecutor
import queue

@dataclass
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

class ImageCache:
    """Thread-safe cache for processed images."""
    
    def __init__(self, max_size: int = 100):
        """
        Initialize the image cache.
        
        Args:
            max_size (int): Maximum number of cached images
        """
        self._cache: Dict[str, Image.Image] = {}
        self._cache_lock = threading.Lock()
        self._max_size = max_size
        self._access_queue = queue.PriorityQueue()
        
    def get(self, key: str) -> Optional[Image.Image]:
        """Get an image from the cache."""
        with self._cache_lock:
            return self._cache.get(key)
            
    def put(self, key: str, image: Image.Image) -> None:
        """Add an image to the cache."""
        with self._cache_lock:
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            self._cache[key] = image
            
    def _evict_oldest(self) -> None:
        """Remove the oldest cached image."""
        if self._cache:
            oldest = min(self._access_queue.queue)
            del self._cache[oldest[1]]
            self._access_queue.get()

class ImageProcessingError(Exception):
    """Custom exception for image processing errors."""
    pass

class ImageProcessor:
    """Handles image processing operations with caching and validation."""
    
    VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
    MAX_IMAGE_SIZE = 10000  # Maximum dimension in pixels
    QUALITY = 95  # Default JPEG quality
    
    def __init__(self):
        """Initialize the image processor."""
        self._cache = ImageCache()
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
                
            # Verify file type
            if not imghdr.what(str(path)):
                return False
                
            # Validate image data
            with Image.open(path) as img:
                img.verify()
                
            return True
        except Exception as e:
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
            # Generate cache key
            cache_key = self._generate_cache_key(image_path, operations)
            
            # Check cache
            cached_result = self._cache.get(cache_key)
            if cached_result:
                return cached_result
                
            # Process image
            with Image.open(image_path) as img:
                result = self._apply_operations(img, operations)
                
                # Cache result
                self._cache.put(cache_key, result)
                
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
        result = image.copy()
        
        for operation in operations:
            op_type = operation.get('type')
            params = operation.get('params', {})
            
            if op_type == 'resize':
                result = self._resize_image(result, **params)
            elif op_type == 'rotate':
                result = self._rotate_image(result, **params)
            elif op_type == 'adjust_brightness':
                result = self._adjust_brightness(result, **params)
            elif op_type == 'adjust_contrast':
                result = self._adjust_contrast(result, **params)
            elif op_type == 'crop':
                result = self._crop_image(result, **params)
            elif op_type == 'filter':
                result = self._apply_filter(result, **params)
            else:
                logging.warning(f"Unknown operation type: {op_type}")
                
        return result
        
    @staticmethod
    def _resize_image(image: Image.Image, size: Tuple[int, int], keep_aspect: bool = True) -> Image.Image:
        """Resize an image."""
        if keep_aspect:
            return image.resize(size, Image.Resampling.LANCZOS)
        return image.thumbnail(size, Image.Resampling.LANCZOS)
        
    @staticmethod
    def _rotate_image(image: Image.Image, angle: float, expand: bool = True) -> Image.Image:
        """Rotate an image."""
        return image.rotate(angle, expand=expand, resample=Image.Resampling.BICUBIC)
        
    @staticmethod
    def _adjust_brightness(image: Image.Image, factor: float) -> Image.Image:
        """Adjust image brightness."""
        enhancer = ImageEnhance.Brightness(image)
        return enhancer.enhance(factor)
        
    @staticmethod
    def _adjust_contrast(image: Image.Image, factor: float) -> Image.Image:
        """Adjust image contrast."""
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(factor)
        
    @staticmethod
    def _crop_image(image: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
        """Crop an image."""
        return image.crop(box)
        
    @staticmethod
    def _apply_filter(image: Image.Image, filter_type: str) -> Image.Image:
        """Apply an image filter."""
        filters = {
            'blur': ImageFilter.BLUR,
            'sharpen': ImageFilter.SHARPEN,
            'smooth': ImageFilter.SMOOTH,
            'edge_enhance': ImageFilter.EDGE_ENHANCE,
            'detail': ImageFilter.DETAIL
        }
        return image.filter(filters.get(filter_type, ImageFilter.BLUR))
        
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
            input_path = Path(path)
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
