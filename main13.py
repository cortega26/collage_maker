import sys
import os
import logging
import json
import glob
from typing import Optional, Dict, List, Tuple
import gc
from dataclasses import dataclass
from datetime import datetime

import psutil

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QSpinBox,
    QHBoxLayout, QPushButton, QFileDialog, QInputDialog, QCheckBox, QLabel,
    QComboBox, QMessageBox, QDialog, QSlider, QDialogButtonBox, QProgressDialog
)
from PySide6.QtCore import (
    Qt, QMimeData, QByteArray, QDataStream, QIODevice, QRect, QSize, QPoint, 
    QFileInfo, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, 
    QAbstractAnimation, QTimer, QDateTime, QThread, QObject,
    Signal, QThreadPool, QRunnable, QMutex, QMutexLocker
)
from PySide6.QtGui import (
    QDrag, QPixmap, QPainter, QImageReader, QColor, QShortcut, QImage, 
    QKeySequence, QFont, QColorSpace
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    handlers=[
        logging.FileHandler("collage_maker.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# Configure global exception handling
def global_exception_handler(exctype, value, traceback):
    try:
        logging.error("Uncaught exception", exc_info=(exctype, value, traceback))
        sys.__excepthook__(exctype, value, traceback)
    except Exception as e:
        sys.stderr.write(f"Error in error handler: {str(e)}\n")

sys.excepthook = global_exception_handler

# Default values
DEFAULT_ROWS = 2
DEFAULT_COLUMNS = 2
DEFAULT_CELL_SIZE = 260
DEFAULT_SPACING = 2

# ========================================================
# Sistema de caché de imágenes
# ========================================================

class ImageCache:
    """Cache system for optimizing image loading and processing while preserving quality."""
    
    def __init__(self):
        self.cache = {}
        self.max_size = 100  # Maximum number of images to cache
        self.mutex = QMutex()  # Thread safety for cache access
        
    def get(self, key: str) -> tuple[Optional[QPixmap], Optional[dict]]:
        """Get an image and its metadata from cache."""
        with QMutexLocker(self.mutex):
            if key in self.cache:
                entry = self.cache[key]
                # Update last access time
                entry['last_access'] = QDateTime.currentDateTime()
                return entry['pixmap'], entry['metadata']
            return None, None
            
    def put(self, key: str, pixmap: QPixmap, metadata: dict):
        """Store an image and its metadata in cache."""
        with QMutexLocker(self.mutex):
            # Create deep copy of pixmap to ensure quality preservation
            cached_pixmap = QPixmap(pixmap)
            
            self.cache[key] = {
                'pixmap': cached_pixmap,
                'metadata': metadata.copy(),
                'last_access': QDateTime.currentDateTime(),
                'size': cached_pixmap.width() * cached_pixmap.height() * 4  # Approximate memory size
            }
            
            # Cleanup if cache is too large
            if len(self.cache) > self.max_size:
                self._cleanup()
                
    def _cleanup(self):
        """Remove least recently used items from cache."""
        if not self.cache:
            return
            
        # Sort by last access time
        items = list(self.cache.items())
        items.sort(key=lambda x: x[1]['last_access'])
        
        # Remove oldest items until we're under max_size
        while len(self.cache) > self.max_size:
            oldest_key = items[0][0]
            del self.cache[oldest_key]
            items.pop(0)
            
    def clear(self):
        """Clear the entire cache."""
        with QMutexLocker(self.mutex):
            self.cache.clear()

# Create global image cache
image_cache = ImageCache()

# ========================================================
# Clase personalizada para transportar imagen en Drag & Drop
# ========================================================

class ImageMimeData(QMimeData):
    def __init__(self, pixmap: QPixmap, source_widget: "CollageCell"):
        super().__init__()
        self._pixmap = pixmap
        self.source_widget = source_widget
        ba = QByteArray()
        stream = QDataStream((ba, QIODevice.WriteOnly))
        stream << pixmap.toImage()
        self.setData("application/x-pixmap", ba)

    def image(self):
        return self._pixmap

# ========================================================
# Optimizador de imágenes
# ========================================================

class ImageOptimizer:
    """Handles image optimization and processing."""
    
    @staticmethod
    def optimize_image(image: QImage, target_size: QSize) -> QImage:
        """Optimize image for display while maintaining maximum quality."""
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32_Premultiplied:
            image = image.convertToFormat(
                QImage.Format_ARGB32_Premultiplied,
                Qt.NoOpaqueDetection  # Preserve alpha quality
            )
        
        # Preserve DPI information
        original_dpmx = image.dotsPerMeterX()
        original_dpmy = image.dotsPerMeterY()
        
        # Calculate optimal size while preserving aspect ratio
        max_dimension = max(target_size.width(), target_size.height())
        if max_dimension > 4000:
            # Scale down in steps for better quality
            intermediate_size = image.size()
            while max(intermediate_size.width(), intermediate_size.height()) > max_dimension:
                scale_factor = 0.75  # Gradual scaling
                intermediate_size *= scale_factor
            
            # Create high-quality scaled version
            scaled = image.scaled(
                intermediate_size.toSize(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        else:
            # Direct scaling for smaller images
            scaled = image.scaled(
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        
        # Restore DPI information
        scaled.setDotsPerMeterX(original_dpmx)
        scaled.setDotsPerMeterY(original_dpmy)
        
        return scaled

    @staticmethod
    def create_high_quality_output(image: QImage, scale_factor: float = 4.0) -> QImage:
        """Create high-quality output version of the image."""
        # Calculate high-resolution size
        target_size = image.size() * scale_factor
        
        # Create high-quality output image
        output = QImage(
            target_size,
            QImage.Format_ARGB32_Premultiplied
        )
        output.fill(Qt.transparent)
        
        # Configure high-quality painter
        painter = QPainter(output)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        # Scale and paint with quality preservation
        painter.scale(scale_factor, scale_factor)
        painter.drawImage(0, 0, image)
        painter.end()
        
        # Preserve DPI information
        if hasattr(image, 'dotsPerMeterX'):
            output.setDotsPerMeterX(image.dotsPerMeterX())
            output.setDotsPerMeterY(image.dotsPerMeterY())
        
        return output
    
    @staticmethod
    def optimize_for_format(image: QImage, format: str) -> QImage:
        """Optimize image for specific output format."""
        if format.lower() in ['jpg', 'jpeg']:
            # Convert to RGB with white background for JPEG
            if image.hasAlphaChannel():
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve DPI
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image
                
        elif format.lower() == 'webp':
            # Convert to ARGB32_Premultiplied for WebP
            if image.format() != QImage.Format_ARGB32_Premultiplied:
                return image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
        
        return image

# ========================================================
# Widget de cada celda del collage (cuadrada)
# ========================================================

class CollageCell(QWidget):
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap = None                # Display version of the image
        self.original_pixmap = None       # Original high-quality version
        self.original_image = None        # Store original QImage for maximum quality
        self.caption = ""                 # Text optional for the image
        self.use_caption_formatting = True  # Master flag for applying format
        self.caption_font_size = 14
        self.caption_bold = True
        self.caption_italic = False
        self.caption_underline = False
        self.transformation_mode = Qt.SmoothTransformation  # Default high quality transformation
        self.aspect_ratio_mode = Qt.KeepAspectRatio        # Default aspect ratio mode
        self.row_span = 1  # Number of rows this cell spans
        self.col_span = 1  # Number of columns this cell spans
        self.setAcceptDrops(True)
        self.setFixedSize(cell_size, cell_size)
        self.setStyleSheet("background-color: transparent;")
        self.selected = False  # Add selected state
        logging.info("Celda %d creada (tamaño %dx%d).", self.cell_id, cell_size, cell_size)

    def setSpan(self, row_span: int, col_span: int):
        """Set the cell's row and column span."""
        self.row_span = max(1, row_span)
        self.col_span = max(1, col_span)
        new_width = self.width() * self.col_span
        new_height = self.height() * self.row_span
        self.setFixedSize(new_width, new_height)
        self.update()
        logging.info(f"Cell {self.cell_id} span updated to {row_span}x{col_span}")

    def setImage(self, pixmap: QPixmap):
        """Set the image for this cell, preserving original quality."""
        # Store the original high quality version
        self.original_pixmap = pixmap
        # Create a display version
        self.pixmap = pixmap.copy()  # Make a copy for display
        self.update()
        logging.info("Cell %d: image loaded and original quality preserved.", self.cell_id)

    def clearImage(self):
        self.pixmap = None
        self.original_pixmap = None
        self.caption = ""
        self.update()

    def paintEvent(self, event):
        """Paint cell content with maximum quality preservation."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        rect = self.rect()
        
        # Draw selection border if selected
        if self.selected:
            pen = painter.pen()
            pen.setColor(QColor(52, 152, 219))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
            
            if any(c.selected for c in self.parent().cells if c != self):
                corner_size = 15
                pen.setColor(QColor(46, 204, 113))
                painter.setPen(pen)
                painter.drawLine(rect.left(), rect.top(), rect.left() + corner_size, rect.top())
                painter.drawLine(rect.left(), rect.top(), rect.left(), rect.top() + corner_size)
                painter.drawLine(rect.right(), rect.bottom(), rect.right() - corner_size, rect.bottom())
                painter.drawLine(rect.right(), rect.bottom(), rect.right(), rect.bottom() - corner_size)
        
        # Draw cell content
        if self.pixmap:
            # Use original high-quality pixmap if available
            source_pixmap = self.original_pixmap if hasattr(self, 'original_pixmap') and self.original_pixmap else self.pixmap
            
            # Scale with maximum quality preservation
            scaled = source_pixmap.scaled(
                rect.size(), 
                self.aspect_ratio_mode,
                Qt.SmoothTransformation  # Always use high quality transformation
            )
            
            # Center the image
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            target = QRect(x, y, scaled.width(), scaled.height())
            
            # Draw with quality preservation
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.drawPixmap(target, scaled, scaled.rect())
            
            # Draw caption if present
            if self.caption:
                self._render_high_quality_caption(painter, target)
                
        else:
            # Draw placeholder with better styling
            painter.fillRect(rect, QColor(245, 245, 245))
            painter.setPen(QColor(180, 180, 180))
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "Drop Image Here\nClick to Select")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() == Qt.ControlModifier:
                # Toggle selection with Ctrl+Click
                self.selected = not self.selected
                self.update()
                logging.info("Celda %d: selección cambiada a %s.", self.cell_id, self.selected)
            elif self.pixmap:
                # Original drag behavior only if there's an image
                logging.info("Celda %d: iniciando drag.", self.cell_id)
                drag = QDrag(self)
                mime_data = ImageMimeData(self.pixmap, self)
                drag.setMimeData(mime_data)
                preview = self.pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(preview)
                result = drag.exec(Qt.MoveAction)
                logging.info("Celda %d: drag finalizado (resultado: %s).", self.cell_id, result)

    def mouseDoubleClickEvent(self, event):
        # Permite editar el caption de la imagen
        if self.pixmap:
            new_caption, ok = QInputDialog.getText(self, "Editar Título", "Título de la imagen:", text=self.caption)
            if ok:
                self.caption = new_caption
                self.update()
                logging.info("Celda %d: caption actualizado a '%s'.", self.cell_id, self.caption)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        logging.info("Celda %d: dropEvent.", self.cell_id)
        mime = event.mimeData()
        # Caso 1: Intercambio interno
        if mime.hasFormat("application/x-pixmap"):
            source_cell = getattr(mime, "source_widget", None)
            if source_cell and source_cell is not self:
                logging.info("Celda %d: intercambiando imagen con Celda %d.", self.cell_id, source_cell.cell_id)
                self.pixmap, source_cell.pixmap = source_cell.pixmap, self.pixmap
                self.original_pixmap, source_cell.original_pixmap = source_cell.original_pixmap, self.original_pixmap
                self.caption, source_cell.caption = source_cell.caption, self.caption
                self.update()
                source_cell.update()
                event.acceptProposedAction()
                return
        # Caso 2: Cargar imagen externa
        elif mime.hasUrls():
            file_path = mime.urls()[0].toLocalFile()
            if file_path:
                self.loadExternalImage(file_path, event)
                return
        event.ignore()

    def loadExternalImage(self, file_path, event):
        """Load external image with maximum quality preservation."""
        try:
            logging.info("Cell %d: loading high-quality image from %s", self.cell_id, file_path)
            
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)  # Apply EXIF orientation
            reader.setQuality(100)  # Maximum quality
            reader.setAllocationLimit(0)  # No memory limits for better quality
            
            # Get original image info
            original_size = reader.size()
            if not original_size.isValid():
                raise ValueError(f"Invalid image size: {reader.errorString()}")
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise ValueError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection  # Preserve alpha channel quality
                )
                # Restore original DPI
                original_image.setDotsPerMeterX(dpmX)
                original_image.setDotsPerMeterY(dpmY)
            
            # Create high-quality pixmap preserving all attributes
            self.original_pixmap = QPixmap.fromImage(original_image)
            self.original_image = original_image  # Keep original for quality preservation
            
            # Create optimized display version
            display_size = self.size()
            if original_size.width() > display_size.width() * 3 or original_size.height() > display_size.height() * 3:
                # Scale down for display while maintaining quality
                self.pixmap = self.original_pixmap.scaled(
                    display_size * 2,  # Keep 2x resolution for quality
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            else:
                # Use original size if not too large
                self.pixmap = self.original_pixmap.copy()
            
            # Cache the original high-quality version
            metadata = {
                'size': original_size,
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'timestamp': QFileInfo(file_path).lastModified()
            }
            image_cache.put(file_path, self.original_pixmap, metadata)
            
            self.update()
            event.acceptProposedAction()
            logging.info(f"Successfully loaded high-quality image in cell {self.cell_id}")
            
        except Exception as e:
            logging.error("Cell %d: Error loading image: %s", self.cell_id, str(e))
            event.ignore()

    def cleanup(self):
        """Clean up resources when cell is destroyed."""
        # Clear image data
        self.pixmap = None
        self.original_pixmap = None
        self.scaled_pixmap = None
        
        # Force garbage collection of large objects
        import gc
        gc.collect()

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()
        # Remove incorrect super().__del__() call since QWidget doesn't have a __del__ method

    def optimize_memory(self):
        """Optimize memory usage by clearing cached scaled images."""
        if hasattr(self, 'scaled_pixmap') and self.scaled_pixmap:
            self.scaled_pixmap = None
            gc.collect()  # Force garbage collection
        
        # Only keep high-quality original if needed
        if self.pixmap and self.original_pixmap:
            # Check if original is significantly larger than displayed size
            orig_size = self.original_pixmap.size()
            display_size = self.size()
            
            if (orig_size.width() > display_size.width() * 2 or 
                orig_size.height() > display_size.height() * 2):
                # Create an optimized version and release the original
                optimized = self.original_pixmap.scaled(
                    display_size * 2,  # Keep 2x resolution for zooming
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.original_pixmap = optimized
                gc.collect()
                
    def batch_process_images(self, image_paths: list):
        """Process multiple images efficiently."""
        for path in image_paths:
            try:
                # Check cache first
                cached_pixmap, metadata = image_cache.get(path)
                if cached_pixmap:
                    self.setImage(cached_pixmap)
                    continue
                
                # Load and process new image
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                
                # Get image info before loading
                size = reader.size()
                if size.width() > 4000 or size.height() > 4000:
                    # Scale down large images
                    scale = 4000 / max(size.width(), size.height())
                    reader.setScaledSize((size * scale).toSize())
                
                image = reader.read()
                if image.isNull():
                    raise ValueError(f"Failed to load image: {reader.errorString()}")
                
                # Convert to optimal format
                if image.format() != QImage.Format_ARGB32:
                    image = image.convertToFormat(QImage.Format_ARGB32)
                
                # Create pixmap and cache it
                pixmap = QPixmap.fromImage(image)
                metadata = {
                    'size': size,
                    'format': reader.format().data().decode(),
                    'timestamp': QFileInfo(path).lastModified()
                }
                image_cache.put(path, pixmap, metadata)
                
                self.setImage(pixmap)
                
            except Exception as e:
                logging.error(f"Error processing image {path}: {str(e)}")
                continue

    def _onImageLoaded(self, pixmap: QPixmap, filename: str):
        """Handle loaded image with quality preservation."""
        try:
            # Store original uncompressed image
            self.original_pixmap = pixmap.copy()  # Make a deep copy of original
            
            # Create display version at cell size while maintaining quality
            display_pixmap = pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Set the display version
            self.setImage(display_pixmap)
            
            # Cache the original high-quality version
            metadata = ImageOptimizer.process_metadata(filename)
            image_cache.put(filename, self.original_pixmap, metadata)
            
            # Close progress dialog if exists
            if hasattr(self, 'progress'):
                self.progress.close()
                delattr(self, 'progress')
                
            # Clean up the loader thread
            if hasattr(self, 'loader'):
                self.loader.deleteLater()
                delattr(self, 'loader')
            
            logging.info(f"Cell {self.cell_id}: Image loaded at original quality")
            
        except Exception as e:
            logging.error(f"Cell {self.cell_id}: Error in image loading: {str(e)}")
            if hasattr(self, 'progress'):
                self.progress.close()
                delattr(self, 'progress')

    def render_high_quality(self, painter: QPainter):
        """Render cell at maximum quality for saving."""
        if not self.pixmap:
            return
            
        rect = self.rect()
        pos = self.mapTo(self.parent(), QPoint(0, 0))
        target_rect = QRect(pos, rect.size())
        
        # Use original high-quality pixmap if available, fall back to regular pixmap if not
        source_pixmap = getattr(self, 'original_pixmap', None) or self.pixmap
        
        # Configure device pixel ratio for high DPI support
        if hasattr(source_pixmap, 'devicePixelRatio'):
            source_pixmap.setDevicePixelRatio(1.0)  # Ensure 1:1 pixel mapping
        
        painter.save()
        # Enable all quality-related render hints
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        # Scale image while preserving aspect ratio and maximum quality
        scaled_pixmap = source_pixmap.scaled(
            target_rect.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Center the image in the cell
        x = target_rect.x() + (target_rect.width() - scaled_pixmap.width()) // 2
        y = target_rect.y() + (target_rect.height() - scaled_pixmap.height()) // 2
        
        # Draw using composition mode that preserves quality
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(x, y, scaled_pixmap)
        
        # Draw caption with optimal quality if present
        if self.caption:
            self._render_high_quality_caption(painter, QRect(x, y, scaled_pixmap.width(), scaled_pixmap.height()))
        
        painter.restore()
        
    def _render_high_quality_caption(self, painter: QPainter, image_rect: QRect):
        """Render caption with maximum quality."""
        font = painter.font()
        if self.use_caption_formatting:
            font.setPointSize(self.caption_font_size)
            font.setBold(self.caption_bold)
            font.setItalic(self.caption_italic)
            font.setUnderline(self.caption_underline)
            # Enable kerning and other font optimizations
            font.setKerning(True)
            font.setHintingPreference(QFont.PreferFullHinting)
        painter.setFont(font)
        
        # Calculate optimal text positioning
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(self.caption)
        text_rect.moveCenter(QPoint(
            image_rect.center().x(),
            image_rect.bottom() - text_rect.height()//2 - 5
        ))
        
        # Draw high-quality text background
        background_rect = text_rect.adjusted(-6, -3, 6, 3)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.fillRect(background_rect, QColor(0, 0, 0, 160))
        
        # Draw text with high-quality anti-aliasing
        painter.setPen(QColor(0, 0, 0, 160))  # Shadow
        painter.drawText(text_rect.adjusted(1, 1, 1, 1), Qt.AlignCenter, self.caption)
        painter.setPen(Qt.white)  # Main text
        painter.drawText(text_rect, Qt.AlignCenter, self.caption)

    def getHighQualityRendering(self) -> QPixmap:
        """Get a high quality rendered version of the cell content."""
        if not self.pixmap:
            return None
            
        # Always use original high-quality pixmap if available
        source_pixmap = self.original_pixmap if hasattr(self, 'original_pixmap') and self.original_pixmap else self.pixmap
        
        # Create target pixmap at desired size
        target_size = self.size()
        output = QPixmap(target_size)
        output.fill(Qt.transparent)
        
        # Set up painter with maximum quality settings
        painter = QPainter(output)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        # Calculate scaling while preserving aspect ratio
        source_rect = source_pixmap.rect()
        target_rect = self.rect()
        
        # Scale and center the image
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(target_rect.size(), Qt.KeepAspectRatio)
            x = (target_rect.width() - scaled_size.width()) // 2
            y = (target_rect.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw with maximum quality
        painter.drawPixmap(target_rect, source_pixmap, source_rect)
        
        # Draw caption if present
        if self.caption:
            self._render_high_quality_caption(painter, target_rect)
        
        painter.end()
        return output
        
    def _create_high_quality_pixmap(self, size: QSize) -> QPixmap:
        """Create a high quality scaled version of the image."""
        if not self.original_pixmap:
            return None
            
        # Create intermediate high-resolution pixmap
        intermediate_size = size * 2  # Work at 2x target size for better quality
        intermediate = QPixmap(intermediate_size)
        intermediate.fill(Qt.transparent)
        
        # High quality painting
        painter = QPainter(intermediate)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Scale while preserving aspect ratio
        source_rect = self.original_pixmap.rect()
        target_rect = QRect(QPoint(0, 0), intermediate_size)
        
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(intermediate_size, Qt.KeepAspectRatio)
            x = (intermediate_size.width() - scaled_size.width()) // 2
            y = (intermediate_size.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw at high resolution
        painter.drawPixmap(target_rect, self.original_pixmap, source_rect)
        painter.end()
        
        # Scale down to target size with high quality
        return intermediate.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _preserve_image_attributes(self, image: QImage, source_image: QImage = None) -> QImage:
        """Preserve image attributes during transformations."""
        if source_image and hasattr(source_image, 'dotsPerMeterX'):
            # Preserve DPI information
            image.setDotsPerMeterX(source_image.dotsPerMeterX())
            image.setDotsPerMeterY(source_image.dotsPerMeterY())
        
        # Ensure optimal color space
        if image.format() != QImage.Format_ARGB32_Premultiplied:
            image = image.convertToFormat(
                QImage.Format_ARGB32_Premultiplied,
                Qt.NoOpaqueDetection  # Preserve alpha channel quality
            )
        
        return image
        
    def scale_with_quality(self, pixmap: QPixmap, target_size: QSize, keep_attributes: bool = True) -> QPixmap:
        """Scale image while preserving maximum quality."""
        if not pixmap:
            return None
            
        # Work at 2x target size for better quality during scaling
        intermediate_size = target_size * 2
        
        # Create intermediate high-resolution pixmap
        intermediate = QPixmap(intermediate_size)
        intermediate.fill(Qt.transparent)
        
        # High quality painting to intermediate
        painter = QPainter(intermediate)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Draw at high resolution
        source_rect = pixmap.rect()
        target_rect = QRect(QPoint(0, 0), intermediate_size)
        
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(intermediate_size, Qt.KeepAspectRatio)
            x = (intermediate_size.width() - scaled_size.width()) // 2
            y = (intermediate_size.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw original image to intermediate
        painter.drawPixmap(target_rect, pixmap, source_rect)
        painter.end()
        
        # Convert to image for attribute preservation
        if keep_attributes:
            intermediate_image = intermediate.toImage()
            source_image = pixmap.toImage()
            intermediate_image = self._preserve_image_attributes(intermediate_image, source_image)
            intermediate = QPixmap.fromImage(intermediate_image)
        
        # Scale down to final size with high quality
        result = intermediate.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Final attribute preservation if needed
        if keep_attributes:
            result_image = result.toImage()
            result_image = self._preserve_image_attributes(result_image, source_image)
            result = QPixmap.fromImage(result_image)
        
        return result

# ========================================================
# Widget del Collage
# ========================================================

class CollageWidget(QWidget):
    """
    Widget para mostrar un grid de CollageCell(s).
    
    Parámetros:
        rows (int): Número de filas.
        columns (int): Número de columnas.
        cell_size (int): Tamaño fijo para cada celda.
    """
    def __init__(self, rows=2, columns=2, cell_size=260, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.cell_size = cell_size
        self.spacing = 2
        self.merged_cells = {}  # Store merged cell information
        self.setup_layout()
        self.setStyleSheet("background-color: black;")
        self.cells = []
        self.populate_grid()
        self.setFixedSize(self.idealSize())

    def setup_layout(self):
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(self.spacing)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.grid_layout)

    def idealSize(self):
        width = self.columns * self.cell_size + (self.columns - 1) * self.spacing
        height = self.rows * self.cell_size + (self.rows - 1) * self.spacing
        return QSize(width, height)

    def populate_grid(self):
        # Limpiar el layout actual
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.cells = []
        total = self.rows * self.columns
        for i in range(self.rows):
            for j in range(self.columns):
                cell_id = i * self.columns + j + 1
                cell = CollageCell(cell_id, self.cell_size, self)
                self.grid_layout.addWidget(cell, i, j)
                self.cells.append(cell)
        logging.info("Collage: creado con %d celdas.", total)

    def merge_cells(self, start_row: int, start_col: int, row_span: int, col_span: int):
        """Merge cells in the specified range into a single cell."""
        # First check if any cell in the range is already merged
        for r in range(start_row, start_row + row_span):
            for c in range(start_col, start_col + col_span):
                # Split any existing merged cells that overlap our target area
                for (mr, mc), (mrs, mcs) in list(self.merged_cells.items()):
                    if (mr <= r < mr + mrs) and (mc <= c < mc + mcs):
                        self.split_merged_cell(mr, mc)
                        break

        # Get the target cell (top-left cell)
        target_cell = self.get_cell_at_position(start_row, start_col)
        if not target_cell:
            logging.warning(f"No cell found at position ({start_row},{start_col})")
            return False

        # Collect all cells to be merged
        cells_to_merge = []
        for r in range(start_row, start_row + row_span):
            for c in range(start_col, start_col + col_span):
                if r == start_row and c == start_col:
                    continue  # Skip target cell
                cell = self.get_cell_at_position(r, c)
                if cell:
                    cells_to_merge.append(cell)

        # Remove other cells from layout and list
        for cell in cells_to_merge:
            self.grid_layout.removeWidget(cell)
            if cell in self.cells:
                self.cells.remove(cell)
            cell.hide()
            cell.deleteLater()

        # Update target cell
        self.grid_layout.removeWidget(target_cell)
        self.grid_layout.addWidget(target_cell, start_row, start_col, row_span, col_span)
        target_cell.row_span = row_span
        target_cell.col_span = col_span
        new_width = self.cell_size * col_span + (col_span - 1) * self.spacing
        new_height = self.cell_size * row_span + (row_span - 1) * self.spacing
        target_cell.setFixedSize(new_width, new_height)

        # Store merge information
        self.merged_cells[(start_row, start_col)] = (row_span, col_span)
        
        logging.info(f"Merged cells at ({start_row},{start_col}) with span {row_span}x{col_span}")
        return True

    def is_valid_merge(self, start_row: int, start_col: int, row_span: int, col_span: int) -> bool:
        """Check if the requested merge operation is valid."""
        # Check bounds
        if (start_row < 0 or start_col < 0 or 
            start_row + row_span > self.rows or 
            start_col + col_span > self.columns):
            logging.warning(f"Merge out of bounds: ({start_row},{start_col}) span {row_span}x{col_span}")
            return False

        # Get set of all selected positions
        selected_positions = set()
        for cell in self.cells:
            if cell.selected:
                pos = self.get_cell_position(cell)
                if pos:
                    # If position is part of a merged cell, get the full merged region
                    is_part_of_merge = False
                    for (mr, mc), (mrs, mcs) in self.merged_cells.items():
                        if (mr <= pos[0] < mr + mrs) and (mc <= pos[1] < mc + mcs):
                            selected_positions.update((r, c) 
                                for r in range(mr, mr + mrs)
                                for c in range(mc, mc + mcs))
                            is_part_of_merge = True
                            break
                    if not is_part_of_merge:
                        selected_positions.add(pos)

        # Check if all required positions are selected
        required_positions = set((r, c) 
            for r in range(start_row, start_row + row_span)
            for c in range(start_col, start_col + col_span))

        if not required_positions.issubset(selected_positions):
            missing = required_positions - selected_positions
            for r, c in missing:
                logging.warning(f"Cell at ({r},{c}) is not selected")
            return False

        return True

    def split_merged_cell(self, row: int, col: int):
        """Split a merged cell back into individual cells."""
        if (row, col) not in self.merged_cells:
            logging.warning(f"No merged cell found at ({row},{col})")
            return False

        # Get merge information
        row_span, col_span = self.merged_cells[row, col]
        
        # Find the merged cell widget
        merged_cell = None
        for cell in self.cells:
            pos = self.get_cell_position(cell)
            if pos and pos == (row, col):
                merged_cell = cell
                break

        if not merged_cell:
            logging.warning("Could not find the merged cell widget")
            return False

        # Store original content and state
        original_pixmap = merged_cell.pixmap
        original_caption = merged_cell.caption
        was_selected = merged_cell.selected

        # Remove merged cell from grid and list
        self.grid_layout.removeWidget(merged_cell)
        if merged_cell in self.cells:
            self.cells.remove(merged_cell)

        # Create new cells
        new_cells = []
        for r in range(row, row + row_span):
            for c in range(col, col + col_span):
                cell_id = len(self.cells) + len(new_cells) + 1
                new_cell = CollageCell(cell_id, self.cell_size, self)
                
                # Only copy content to the top-left cell
                if r == row and c == col:
                    if original_pixmap:
                        new_cell.setImage(original_pixmap)
                    new_cell.caption = original_caption
                    new_cell.selected = was_selected
                
                # Add to grid immediately
                self.grid_layout.addWidget(new_cell, r, c, 1, 1)
                new_cell.show()
                new_cells.append(new_cell)

        # Add new cells to our list
        self.cells.extend(new_cells)

        # Clean up merged cell
        merged_cell.hide()
        merged_cell.deleteLater()

        # Remove merge information
        del self.merged_cells[row, col]

        # Update layout
        self.grid_layout.update()
        
        logging.info(f"Split merged cell at ({row},{col})")
        return True

    def update_grid(self, rows, columns):
        """Update grid dimensions while preserving merged cells where possible."""
        logging.info(f"Updating grid to {rows}x{columns}")
        
        # Store current merges that will still be valid
        valid_merges = {}
        for (row, col), (row_span, col_span) in self.merged_cells.items():
            if (row + row_span <= rows and col + col_span <= columns):
                valid_merges[(row, col)] = (row_span, col_span)

        # Clear current merges
        self.merged_cells.clear()
        
        # Update dimensions
        self.rows = rows
        self.columns = columns
        
        # Rebuild grid
        self.populate_grid()
        
        # Reapply valid merges
        for (row, col), (row_span, col_span) in valid_merges.items():
            self.merge_cells(row, col, row_span, col_span)
        
        self.setFixedSize(self.idealSize())

    def sizeHint(self):
        return self.idealSize()

    def is_cell_merged(self, row: int, col: int) -> bool:
        """Check if the cell at the given position is part of a merged cell."""
        for (mr, mc), (mrs, mcs) in self.merged_cells.items():
            if (mr <= row < mr + mrs) and (mc <= col < mc + mcs):
                return True
        return False

    def get_cell_position(self, cell: CollageCell) -> Optional[tuple[int, int]]:
        """Get the grid position (row, col) of a cell."""
        index = self.grid_layout.indexOf(cell)
        if index != -1:
            item = self.grid_layout.itemAt(index)
            if item:
                # Get actual grid layout position information
                pos = self.grid_layout.getItemPosition(index)
                if pos:
                    row, col, _, _ = pos
                    # Check if this cell is part of a merged cell
                    for (mr, mc), (mrs, mcs) in self.merged_cells.items():
                        if row == mr and col == mc:
                            # This is the main merged cell
                            return (mr, mc)
                        elif (mr <= row < mr + mrs) and (mc <= col < mc + mcs):
                            # This is part of a merged cell, return None
                            return None
                    # Regular cell, return its position
                    return (row, col)
        return None

    def get_cell_at_position(self, row: int, col: int) -> Optional[CollageCell]:
        """Get the cell at a specific grid position, if it exists."""
        # First check for merged cells
        for (mr, mc), (mrs, mcs) in self.merged_cells.items():
            if row == mr and col == mc:
                # Found a merged cell's top-left position
                for i in range(self.grid_layout.count()):
                    item = self.grid_layout.itemAt(i)
                    if item and isinstance(item.widget(), CollageCell):
                        pos = self.grid_layout.getItemPosition(i)
                        if pos and pos[0] == row and pos[1] == col:
                            return item.widget()

        # If not a merged cell, check regular positions
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and isinstance(item.widget(), CollageCell):
                pos = self.grid_layout.getItemPosition(i)
                if pos and pos[0] == row and pos[1] == col:
                    return item.widget()
        return None

    def merge_selected_cells(self):
        """Merge all selected cells into a single cell."""
        # Get selected cells and their positions
        selected = []
        for cell in self.cells:
            if cell.selected:
                pos = self.get_cell_position(cell)
                if pos:
                    selected.append((cell, pos))

        if len(selected) < 2:
            logging.warning("Need at least 2 cells selected for merging")
            return

        # Find boundaries
        min_row = min(pos[0] for _, pos in selected)
        min_col = min(pos[1] for _, pos in selected)
        max_row = max(pos[0] for _, pos in selected)
        max_col = max(pos[1] for _, pos in selected)

        # Calculate spans
        row_span = max_row - min_row + 1
        col_span = max_col - min_col + 1

        # Create set of all selected positions
        selected_positions = {pos for _, pos in selected}

        # Verify selection forms a continuous rectangle
        for r in range(min_row, min_row + row_span):
            for c in range(min_col, min_col + col_span):
                if (r, c) not in selected_positions:
                    logging.warning(f"Selection must form a continuous rectangle")
                    return

        # Get target cell (top-left)
        target_cell = None
        for cell, pos in selected:
            if pos == (min_row, min_col):
                target_cell = cell
                break

        if not target_cell:
            return

        # Split any existing merged cells in our selection range
        for _, (row, col) in selected:
            for (mr, mc), (mrs, mcs) in list(self.merged_cells.items()):
                if (mr <= row < mr + mrs) and (mc <= col < mc + mcs):
                    self.split_merged_cell(mr, mc)

        # Remove other cells
        for cell, _ in selected:
            if cell != target_cell:
                self.grid_layout.removeWidget(cell)
                if cell in self.cells:
                    self.cells.remove(cell)
                cell.hide()
                cell.deleteLater()

        # Update target cell
        self.grid_layout.removeWidget(target_cell)
        self.grid_layout.addWidget(target_cell, min_row, min_col, row_span, col_span)
        target_cell.row_span = row_span
        target_cell.col_span = col_span
        new_width = self.cell_size * col_span + (col_span - 1) * self.spacing
        new_height = self.cell_size * row_span + (row_span - 1) * self.spacing
        target_cell.setFixedSize(new_width, new_height)

        # Store merge info
        self.merged_cells[(min_row, min_col)] = (row_span, col_span)

        # Clear selection
        target_cell.selected = False
        target_cell.update()

        logging.info(f"Merged cells at ({min_row},{min_col}) with span {row_span}x{col_span}")
        return True

    def animate_swap(self, source_cell, target_cell):
        """Animate image swap between cells."""
        if not (source_cell.pixmap and hasattr(source_cell, 'pos') and hasattr(target_cell, 'pos')):
            return

        # Create animation widgets
        anim1 = QLabel(self.collage)
        anim2 = QLabel(self.collage)
        
        # Set up initial positions and images
        source_pos = source_cell.mapTo(self.collage, QPoint(0, 0))
        target_pos = target_cell.mapTo(self.collage, QPoint(0, 0))
        
        anim1.setPixmap(source_cell.pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if target_cell.pixmap:
            anim2.setPixmap(target_cell.pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        anim1.setGeometry(QRect(source_pos, source_cell.size()))
        anim2.setGeometry(QRect(target_pos, target_cell.size()))
        
        anim1.show()
        anim2.show() if target_cell.pixmap else None
        
        # Create and configure animation group
        animation_group = QParallelAnimationGroup()
        
        # Position animations
        anim1_pos = QPropertyAnimation(anim1, b"geometry")
        anim1_pos.setDuration(300)
        anim1_pos.setStartValue(QRect(source_pos, source_cell.size()))
        anim1_pos.setEndValue(QRect(target_pos, target_cell.size()))
        anim1_pos.setEasingCurve(QEasingCurve.InOutCubic)
        
        if target_cell.pixmap:
            anim2_pos = QPropertyAnimation(anim2, b"geometry")
            anim2_pos.setDuration(300)
            anim2_pos.setStartValue(QRect(target_pos, target_cell.size()))
        animation_group.finished.connect(lambda: self.cleanup_animation(anim1, anim2))
        
        # Start animation
        animation_group.start(QAbstractAnimation.DeleteWhenStopped)
        self.target_cell.caption = self.source_caption
        self.source_cell.update()
        self.target_cell.update()

class UndoStack:
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []

    def push(self, command):
        command.redo()  # Execute the command
        self.undo_stack.append(command)
        self.redo_stack.clear()  # Clear redo stack when new command is pushed

    def undo(self):
        if self.undo_stack:
            command = self.undo_stack.pop()
            command.undo()
            self.redo_stack.append(command)

    def redo(self):
        if self.redo_stack:
            command = self.redo_stack.pop()
            command.redo()
            self.undo_stack.append(command)

    def clear(self):
        self.undo_stack.clear()
        self.redo_stack.clear()

# ========================================================
# Worker, TaskQueue, and related classes
# ========================================================

class WorkerSignals(QObject):
    """Defines signals for worker threads."""
    started = Signal()
    finished = Signal()
    error = Signal(str)
    progress = Signal(int)
    result = Signal(object)

class Worker(QRunnable):
    """Base worker class for background tasks."""
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
    def run(self):
        """Execute the task."""
        try:
            self.signals.started.emit()
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

class TaskQueue:
    """Manages queued tasks with priority handling."""
    def __init__(self, max_concurrent=4):
        self.queue = []
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(max_concurrent)
        self.mutex = QMutex()
        self.processing = False

    def add_task(self, task, priority=0):
        """Add a task to the queue with optional priority."""
        with QMutexLocker(self.mutex):
            self.queue.append((priority, task))
            self.queue.sort(key=lambda x: x[0], reverse=True)
            
        if not self.processing:
            self.process_next()

    def process_next(self):
        """Process the next task in the queue."""
        with QMutexLocker(self.mutex):
            if not self.queue:
                self.processing = False
                return
                
            self.processing = True
            _, task = self.queue.pop(0)
            
        self.thread_pool.start(task)
        task.signals.finished.connect(self.process_next)

    def clear(self):
        """Clear all pending tasks."""
        with QMutexLocker(self.mutex):
            self.queue.clear()

    def is_empty(self):
        """Check if queue is empty."""
        with QMutexLocker(self.mutex):
            return len(self.queue) == 0

class ImageLoadWorker(QThread):
    """Worker thread for loading and processing images with maximum quality preservation."""
    finished = Signal(QPixmap, str)  # Emits processed pixmap and filename
    error = Signal(str)  # Emits error message if loading fails
    progress = Signal(int)  # Emits progress percentage
    
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._cancelled = False
        
    def run(self):
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(self.file_path)
            reader.setAutoTransform(True)  # Apply EXIF orientation
            reader.setQuality(100)  # Maximum quality
            reader.setAllocationLimit(0)  # No memory limits
            
            # Get image info before loading
            original_size = reader.size()
            if not original_size.isValid():
                self.error.emit(f"Invalid image size: {reader.errorString()}")
                return
                
            # Load image at original resolution, no scaling
            original_image = reader.read()
            if original_image.isNull():
                self.error.emit(f"Failed to load image: {reader.errorString()}")
                return
                
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32:
                original_image = original_image.convertToFormat(QImage.Format_ARGB32)
                
            # Create high-quality pixmap preserving all attributes
            self.original_pixmap = QPixmap.fromImage(original_image)
            
            # Store original DPI if available
            if hasattr(original_image, 'dotsPerMeterX'):
                self.original_pixmap.setDevicePixelRatio(
                    original_image.dotsPerMeterX() / 39370.0  # Convert to standard DPI
                )
            
            self.finished.emit(self.original_pixmap, self.file_path)
            
        except Exception as e:
            self.error.emit(str(e))
            
    def cancel(self):
        self._cancelled = True

class BatchProcessor:
    """Handles batch processing of multiple images."""
    def __init__(self, parent):
        self.parent = parent
        self.processing_queue = []
        self.current_worker = None
        
    def process_files(self, file_paths: list, target_size: QSize = None):
        """Start batch processing of files."""
        self.processing_queue = file_paths
        
        # Create and configure progress dialog
        progress = QProgressDialog("Processing images...", "Cancel", 0, len(file_paths), self.parent)
        progress.setWindowModality(Qt.WindowModal)
        
        # Create worker thread
        self.current_worker = ImageLoadWorker(file_paths, target_size)
        
        # Connect signals
        self.current_worker.finished.connect(self._on_image_processed)
        self.current_worker.error.connect(self._on_error)
        self.current_worker.progress.connect(progress.setValue)
        progress.canceled.connect(self.current_worker.cancel)
        
        # Start processing
        self.current_worker.start()
        progress.exec_()
        
    def _on_image_processed(self, pixmap: QPixmap, file_path: str):
        """Handle processed image."""
        # Add to cache
        metadata = ImageOptimizer.process_metadata(file_path)
        image_cache.put(file_path, pixmap, metadata)
        
    def _on_error(self, error_message: str):
        """Handle processing error."""
        QMessageBox.warning(
            self.parent,
            "Processing Error",
            error_message
        )

class AutosaveManager:
    """Manages automatic saving of collage state."""
    def __init__(self, parent):
        self.parent = parent
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self.perform_autosave)
        self.autosave_interval = 5 * 60 * 1000  # 5 minutes in milliseconds
        self.autosave_path = "autosave"
        self.ensure_autosave_dir()
        
    def ensure_autosave_dir(self):
        """Ensure autosave directory exists."""
        if not os.path.exists(self.autosave_path):
            os.makedirs(self.autosave_path)
            
    def start(self):
        """Start autosave timer."""
        self.autosave_timer.start(self.autosave_interval)
        
    def stop(self):
        """Stop autosave timer."""
        self.autosave_timer.stop()
        
    def perform_autosave(self):
        """Perform the autosave operation."""
        try:
            # Generate autosave filename with timestamp
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
            filename = f"collage_autosave_{timestamp}.json"
            filepath = os.path.join(self.autosave_path, filename)
            
            # Get collage state
            state = self.parent.get_collage_state()
            
            # Save state to file
            with open(filepath, 'w') as f:
                json.dump(state, f)
                
            # Clean up old autosaves (keep last 5)
            self.cleanup_old_autosaves()
            
            logging.info(f"Autosave completed: {filepath}")
            
        except Exception as e:
            logging.error(f"Autosave failed: {str(e)}")
            
    def cleanup_old_autosaves(self):
        """Keep only the 5 most recent autosaves."""
        try:
            files = glob.glob(os.path.join(self.autosave_path, "collage_autosave_*.json"))
            files.sort(reverse=True)
            
            # Remove old files
            for old_file in files[5:]:
                try:
                    os.remove(old_file)
                except:
                    pass
                    
        except Exception as e:
            logging.error(f"Autosave cleanup failed: {str(e)}")
            
    def get_latest_autosave(self):
        """Get the most recent autosave file."""
        try:
            files = glob.glob(os.path.join(self.autosave_path, "collage_autosave_*.json"))
            if files:
                return max(files, key=os.path.getctime)
        except Exception as e:
            logging.error(f"Failed to get latest autosave: {str(e)}")
        return None

class PerformanceMonitor:
    """Monitors and optimizes application performance."""
    def __init__(self):
        self.memory_threshold = 500 * 1024 * 1024  # 500MB
        self.last_cleanup = QDateTime.currentDateTime()
        self.cleanup_interval = 300  # 5 minutes in seconds
        
    def check_memory_usage(self):
        """Check current memory usage and optimize if needed."""
        try:
            if HAS_PSUTIL:
                process = psutil.Process()
                memory_info = process.memory_info()
                
                if memory_info.rss > self.memory_threshold:
                    current_time = QDateTime.currentDateTime()
                    if self.last_cleanup.secsTo(current_time) >= self.cleanup_interval:
                        self.optimize_memory_usage()
                        self.last_cleanup = current_time
                    
        except Exception as e:
            logging.warning(f"Memory monitoring error: {str(e)}")
            
    def optimize_memory_usage(self):
        """Perform memory optimization."""
        # Clear image cache if too large
        if len(image_cache.cache) > image_cache.max_size * 0.8:
            image_cache._cleanup()
            
        # Force Python garbage collection
        gc.collect()
        
        logging.info("Memory optimization performed")

class ErrorHandlingManager:
    """Manages error handling and recovery for image operations."""
    
    class ImageOperationError(Exception):
        """Base exception for image operations."""
        pass
        
    class LoadError(ImageOperationError):
        """Error loading an image."""
        pass
        
    class SaveError(ImageOperationError):
        """Error saving an image."""
        pass
        
    class FormatError(ImageOperationError):
        """Error with image format."""
        pass
        
    class MemoryError(ImageOperationError):
        """Error with memory allocation."""
        pass
    
    def __init__(self):
        self.error_handlers = {
            'load': self._handle_load_error,
            'save': self._handle_save_error,
            'format': self._handle_format_error,
            'memory': self._handle_memory_error
        }
        
    def handle_error(self, operation: str, error: Exception, context: dict = None) -> bool:
        """Handle an error during image operations."""
        try:
            if operation in self.error_handlers:
                return self.error_handlers[operation](error, context or {})
            return self._handle_unknown_error(error, context or {})
        except Exception as e:
            logging.error(f"Error in error handler: {str(e)}")
            return False
            
    def _handle_load_error(self, error: Exception, context: dict) -> bool:
        """Handle image loading errors."""
        file_path = context.get('file_path', 'unknown')
        error_msg = str(error)
        
        if 'Permission denied' in error_msg:
            logging.error(f"Permission denied accessing {file_path}")
            return False
            
        if 'No such file' in error_msg:
            logging.error(f"File not found: {file_path}")
            return False
            
        if 'Invalid format' in error_msg:
            logging.error(f"Invalid image format: {file_path}")
            return False
            
        logging.error(f"Unknown error loading image {file_path}: {error_msg}")
        return False
        
    def _handle_save_error(self, error: Exception, context: dict) -> bool:
        """Handle image saving errors."""
        file_path = context.get('file_path', 'unknown')
        format = context.get('format', 'unknown')
        
        if isinstance(error, IOError):
            if 'Permission denied' in str(error):
                logging.error(f"Permission denied saving to {file_path}")
                return False
                
            if 'No space' in str(error):
                logging.error(f"No disk space available saving to {file_path}")
                return False
                
        if isinstance(error, ValueError):
            if 'format' in str(error).lower():
                logging.error(f"Unsupported format {format} for {file_path}")
                return False
                
        logging.error(f"Unknown error saving image {file_path}: {str(error)}")
        return False
        
    def _handle_format_error(self, error: Exception, context: dict) -> bool:
        """Handle format conversion errors."""
        source_format = context.get('source_format', 'unknown')
        target_format = context.get('target_format', 'unknown')
        
        if 'Unsupported conversion' in str(error):
            logging.error(f"Unsupported conversion from {source_format} to {target_format}")
            return False
            
        if 'Invalid format' in str(error):
            logging.error(f"Invalid format specified: {target_format}")
            return False
            
        logging.error(f"Unknown format error converting {source_format} to {target_format}: {str(error)}")
        return False
        
    def _handle_memory_error(self, error: Exception, context: dict) -> bool:
        """Handle memory-related errors."""
        operation = context.get('operation', 'unknown')
        size = context.get('size', 'unknown')
        
        if isinstance(error, MemoryError):
            logging.error(f"Memory allocation failed for {operation} (size: {size})")
            return False
            
        logging.error(f"Unknown memory error during {operation}: {str(error)}")
        return False
        
    def _handle_unknown_error(self, error: Exception, context: dict) -> bool:
        """Handle unknown errors."""
        operation = context.get('operation', 'unknown')
        logging.error(f"Unknown error during {operation}: {str(error)}")
        return False

# ========================================================
# Ventana Principal
# ========================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker - PySide6")
        self.resize(850, 650)
        
        # Initialize undo stack
        self.undo_stack = UndoStack()
        
        # Create keyboard shortcuts
        self.create_shortcuts()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.addLayout(self.create_controls_panel())
        self.collage = CollageWidget(rows=self.rows_spin.value(), columns=self.cols_spin.value(), cell_size=260)
        main_layout.addWidget(self.collage, alignment=Qt.AlignCenter)
        logging.info("Ventana principal inicializada.")
        
        # Initialize autosave manager
        self.autosave_manager = AutosaveManager(self)
        self.autosave_manager.start()
        
        # Check for autosave
        self.check_for_autosave()
        self.batch_processor = BatchProcessor(self)
        
        # Initialize performance monitor
        self.performance_monitor = PerformanceMonitor()
        
        # Initialize error recovery manager
        self.error_recovery_manager = ErrorRecoveryManager(self)
        
        # Initialize save manager
        self.save_manager = SaveManager()
        
    def handle_batch_import(self):
        """Handle batch import of multiple images."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
        )
        
        if file_paths:
            # Calculate target size based on cell dimensions
            target_size = QSize(
                self.collage.cell_size * 2,  # 2x cell size for high quality
                self.collage.cell_size * 2
            )
            
            # Start batch processing
            self.batch_processor.process_files(file_paths, target_size)
            
    def create_shortcuts(self):
        """Create keyboard shortcuts for common actions."""
        # Undo/Redo shortcuts
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self.undo_action)
        
        redo_shortcut = QShortcut(QKeySequence.Redo, self)
        redo_shortcut.activated.connect(self.redo_action)
        
        # Save shortcut
        save_shortcut = QShortcut(QKeySequence.Save, self)
        save_shortcut.activated.connect(self.save_collage)
        
        # Delete selection shortcut
        delete_shortcut = QShortcut(QKeySequence.Delete, self)
        delete_shortcut.activated.connect(self.delete_selected)
        
        # Select all shortcut
        select_all_shortcut = QShortcut(QKeySequence.SelectAll, self)
        select_all_shortcut.activated.connect(self.select_all_cells)
        
        # Deselect shortcut
        deselect_shortcut = QShortcut(QKeySequence("Escape"), self)
        deselect_shortcut.activated.connect(self.deselect_all_cells)
        
        # Merge/Split shortcuts
        merge_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        merge_shortcut.activated.connect(self.merge_selected_cells)
        
        split_shortcut = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        split_shortcut.activated.connect(self.split_selected_cell)

    def undo_action(self):
        """Handle undo action."""
        self.undo_stack.undo()
        self.update()
        logging.info("Undo action performed")

    def redo_action(self):
        """Handle redo action."""
        self.undo_stack.redo()
        self.update()
        logging.info("Redo action performed")

    def delete_selected(self):
        """Clear images from selected cells."""
        for cell in self.collage.cells:
            if cell.selected:
                cell.clearImage()
        logging.info("Deleted images from selected cells")

    def select_all_cells(self):
        """Select all cells in the collage."""
        for cell in self.collage.cells:
            cell.selected = True
            cell.update()
        logging.info("Selected all cells")

    def deselect_all_cells(self):
        """Deselect all cells in the collage."""
        for cell in self.collage.cells:
            cell.selected = False
            cell.update()
        logging.info("Deselected all cells")

    def create_controls_panel(self):
        controls_layout = QHBoxLayout()

        # Create a group for grid controls
        grid_group = QHBoxLayout()
        grid_group.addWidget(QLabel("Grid:"))
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setValue(2)
        self.rows_spin.setPrefix("Rows: ")
        self.rows_spin.setToolTip("Set number of rows in the grid")
        
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1)
        self.cols_spin.setValue(2)
        self.cols_spin.setPrefix("Cols: ")
        self.cols_spin.setToolTip("Set number of columns in the grid")
        
        update_button = QPushButton("Update Grid")
        update_button.setToolTip("Apply grid size changes")
        update_button.clicked.connect(self.update_collage)
        
        grid_group.addWidget(self.rows_spin)
        grid_group.addWidget(self.cols_spin)
        grid_group.addWidget(update_button)

        # Create a group for merge/split controls with better styling
        merge_group = QHBoxLayout()
        merge_group.addWidget(QLabel("Cell Operations:"))
        
        merge_button = QPushButton("Merge Cells")
        merge_button.setToolTip("Merge selected cells (Ctrl+M)\nSelect multiple cells with Ctrl+Click")
        merge_button.clicked.connect(self.merge_selected_cells)
        merge_button.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                background-color: #4CAF50;
                color: white;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        split_button = QPushButton("Split Cell")
        split_button.setToolTip("Split merged cell back to individual cells (Ctrl+Shift+M)")
        split_button.clicked.connect(self.split_selected_cell)
        split_button.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                background-color: #2196F3;
                color: white;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
        """)
        
        merge_group.addWidget(merge_button)
        merge_group.addWidget(split_button)

        # Create save/export controls
        save_group = QHBoxLayout()
        save_button = QPushButton("Save Collage")
        save_button.setToolTip("Save the collage as an image (Ctrl+S)")
        save_button.clicked.connect(self.save_collage)
        
        batch_import_button = QPushButton("Batch Import")
        batch_import_button.setToolTip("Import multiple images at once")
        batch_import_button.clicked.connect(self.handle_batch_import)
        
        save_group.addWidget(save_button)
        save_group.addWidget(batch_import_button)

        # Layout vertical para organizar los controles
        controls_vertical = QVBoxLayout()
        
        # First row with main controls
        row1 = QHBoxLayout()
        row1.addLayout(grid_group)
        row1.addSpacing(20)  # Add spacing between groups
        row1.addLayout(merge_group)
        row1.addSpacing(20)
        row1.addLayout(save_group)
        row1.addStretch()  # Push everything to the left
        
        # Image quality controls with better organization
        quality_group = QHBoxLayout()
        quality_group.addWidget(QLabel("Image Quality:"))
        
        self.transform_combo = QComboBox()
        self.transform_combo.addItem("Lossless Quality", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("High Quality", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("Balanced", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("Fast", Qt.TransformationMode.FastTransformation)
        self.transform_combo.setCurrentIndex(0)  # Set Lossless as default
        self.transform_combo.currentIndexChanged.connect(self.update_image_quality)
        self.transform_combo.setToolTip("Select image transformation quality\nLossless: Preserves original quality\nHigh Quality: Very good quality\nBalanced: Good quality with better performance\nFast: Faster but lower quality")
        
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItem("Keep Aspect Ratio", Qt.KeepAspectRatio)
        self.aspect_combo.addItem("Stretch to Fill", Qt.IgnoreAspectRatio)
        self.aspect_combo.addItem("Fit Inside", Qt.KeepAspectRatioByExpanding)
        self.aspect_combo.setCurrentIndex(0)
        self.aspect_combo.currentIndexChanged.connect(self.update_image_quality)
        self.aspect_combo.setToolTip("Select how images should fit in cells")
        
        quality_group.addWidget(self.transform_combo)
        quality_group.addWidget(self.aspect_combo)
        quality_group.addStretch()

        # Caption controls with better organization
        caption_group = QHBoxLayout()
        caption_group.addWidget(QLabel("Caption Format:"))
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 36)
        self.font_size_spin.setValue(14)
        self.font_size_spin.setPrefix("Size: ")
        self.font_size_spin.valueChanged.connect(self.update_caption_format)
        self.font_size_spin.setToolTip("Set caption font size")

        self.bold_checkbox = QCheckBox("Bold")
        self.bold_checkbox.setChecked(True)
        self.bold_checkbox.toggled.connect(self.update_caption_format)
        
        self.italic_checkbox = QCheckBox("Italic")
        self.italic_checkbox.setChecked(False)
        self.italic_checkbox.toggled.connect(self.update_caption_format)
        
        self.underline_checkbox = QCheckBox("Underline")
        self.underline_checkbox.setChecked(False)
        self.underline_checkbox.toggled.connect(self.update_caption_format)
        
        caption_group.addWidget(self.font_size_spin)
        caption_group.addWidget(self.bold_checkbox)
        caption_group.addWidget(self.italic_checkbox)
        caption_group.addWidget(self.underline_checkbox)
        caption_group.addStretch()

        # Add all groups to the main vertical layout
        controls_vertical.addLayout(row1)
        controls_vertical.addSpacing(10)
        controls_vertical.addLayout(quality_group)
        controls_vertical.addSpacing(10)
        controls_vertical.addLayout(caption_group)
        
        return controls_vertical

    def merge_selected_cells(self):
        """Handle merge cells action from UI."""
        self.collage.merge_selected_cells()

    def split_selected_cell(self):
        """Handle split cell action from UI."""
        selected_cells = [cell for cell in self.collage.cells if cell.selected]
        if not selected_cells:
            QMessageBox.warning(self, "Split Cell", "Please select a merged cell to split")
            return

        # Find any merged cell in selection
        for cell in selected_cells:
            pos = self.collage.get_cell_position(cell)
            if pos:
                row, col = pos
                # Check if this is a merged cell or part of one
                merged_found = False
                for (mr, mc), (mrs, mcs) in list(self.collage.merged_cells.items()):
                    if (mr <= row < mr + mrs) and (mc <= col < mc + mcs):
                        # Found a merged cell, attempt to split it
                        if self.collage.split_merged_cell(mr, mc):
                            merged_found = True
                            break
                if merged_found:
                    break
        else:
            QMessageBox.warning(self, "Split Cell", "Selected cell is not merged")

    def update_caption_format(self):
        # Obtener valores actuales de los controles
        font_size = self.font_size_spin.value()
        bold = self.bold_checkbox.isChecked()
        italic = self.italic_checkbox.isChecked()
        underline = self.underline_checkbox.isChecked()
        # Actualizar cada celda del collage
        for cell in self.collage.cells:
            cell.use_caption_formatting = True
            cell.caption_font_size = font_size
            cell.caption_bold = bold
            cell.caption_italic = italic
            cell.caption_underline = underline
            cell.update()
        logging.info("Formato caption actualizado: tamaño=%d, bold=%s, italic=%s, underline=%s",
                     font_size, bold, italic, underline)

    def handle_error(self, message: str, detailed_error: str = None):
        """Handle errors with proper user feedback."""
        QMessageBox.critical(
            self,
            "Error",
            message + ("\n\nDetailed error:\n" + detailed_error if detailed_error else None
        ))
        logging.error(message + (f": {detailed_error}" if detailed_error else ""))

    def update_image_quality(self):
        try:
            # Update quality settings for all cells
            transform_mode = self.transform_combo.currentData()
            aspect_mode = self.aspect_combo.currentData()
            
            # Store current cursor
            current_cursor = self.cursor()
            self.setCursor(Qt.WaitCursor)
            
            # Batch update all cells
            for cell in self.collage.cells:
                if cell.pixmap:  # Only process cells with images
                    cell.transformation_mode = transform_mode
                    cell.aspect_ratio_mode = aspect_mode
                    if cell.original_pixmap:
                        # Regenerate scaled version from original
                        cell.pixmap = cell.original_pixmap
                    cell.update()
            
            # Restore cursor
            self.setCursor(current_cursor)
            
            logging.info("Image quality updated: transform=%s, aspect=%s",
                        self.transform_combo.currentText(),
                        self.aspect_combo.currentText())
                        
        except Exception as e:
            self.handle_error("Failed to update image quality", str(e))
            
    def closeEvent(self, event):
        """Handle application closure."""
        try:
            # Clean up any temporary files or resources
            for cell in self.collage.cells:
                if hasattr(cell, 'cleanup'):
                    cell.cleanup()
                    
            # Save application state/settings if needed
            logging.info("Application closing, cleanup complete")
            event.accept()
            
        except Exception as e:
            self.handle_error("Error during cleanup", str(e))
            event.ignore()  # Prevent closure if cleanup failed

    def update_collage(self):
        rows = self.rows_spin.value()
        columns = self.cols_spin.value()
        logging.info("Actualizando collage: %d filas x %d columnas.", rows, columns)
        self.collage.update_grid(rows, columns)

    def save_collage(self):
        self.save_manager.save_collage(self.collage, self)

    def show_save_dialog(self):
        """Show advanced save dialog with preview and options."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Save Collage")
        dialog.setMinimumWidth(600)
        
        layout = QVBoxLayout(dialog)
        
        # Preview
        preview_label = QLabel()
        preview_pixmap = self.collage.grab().scaled(
            300, 300, 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        preview_label.setPixmap(preview_pixmap)
        layout.addWidget(preview_label, alignment=Qt.AlignCenter)
        
        # Format selection
        format_layout = QHBoxLayout()
        format_label = QLabel("Format:")
        format_combo = QComboBox()
        format_combo.addItems(["PNG", "JPEG", "WebP"])
        format_layout.addWidget(format_label)
        format_layout.addWidget(format_combo)
        layout.addLayout(format_layout)
        
        # Quality settings
        quality_layout = QHBoxLayout()
        quality_label = QLabel("Quality:")
        quality_slider = QSlider(Qt.Horizontal)
        quality_slider.setRange(1, 100)
        quality_slider.setValue(95)
        quality_value = QLabel("95%")
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(quality_slider)
        quality_layout.addWidget(quality_value)
        layout.addLayout(quality_layout)
        
        # Resolution multiplier
        resolution_layout = QHBoxLayout()
        resolution_label = QLabel("Resolution:")
        resolution_combo = QComboBox()
        resolution_combo.addItems(["1x", "2x", "4x"])
        resolution_layout.addWidget(resolution_label)
        resolution_layout.addWidget(resolution_combo)
        layout.addLayout(resolution_layout)
        
        # Connect quality slider to label
        quality_slider.valueChanged.connect(
            lambda v: quality_value.setText(f"{v}%")
        )
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.Accepted:
            return {
                'format': format_combo.currentText().lower(),
                'quality': quality_slider.value(),
                'resolution': int(resolution_combo.currentText()[0])
            }
        return None

    def optimize_for_format(self, pixmap: QPixmap, format: str, quality: int) -> QPixmap:
        """Optimize pixmap for specific output format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB for JPEG (removes alpha channel)
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)  # White background
                painter = QPainter(rgb_image)
                painter.drawImage(0, 0, image)
                painter.end()
                return QPixmap.fromImage(rgb_image)
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        # PNG doesn't need special handling
        return pixmap

    def save_collage_with_options(self, options: dict):
        """Save collage with advanced options."""
        try:
            format = options['format']
            quality = options['quality']
            scale = options['resolution']
            
            # Calculate output size
            base_size = self.collage.size()
            output_size = QSize(
                base_size.width() * scale,
                base_size.height() * scale
            )
            
            # Create high-res pixmap
            output_pixmap = QPixmap(output_size)
            output_pixmap.fill(Qt.transparent)
            
            # Set up painter with high quality settings
            painter = QPainter(output_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while preserving aspect ratio
            source_rect = self.collage.rect()
            target_rect = QRect(QPoint(0, 0), output_size)
            
            # Scale and center the image
            if self.collage.aspect_ratio_mode == Qt.KeepAspectRatio:
                scaled_size = source_rect.size().scaled(target_rect.size(), Qt.KeepAspectRatio)
                x = (target_rect.width() - scaled_size.width()) // 2
                y = (target_rect.height() - scaled_size.height()) // 2
                target_rect = QRect(QPoint(x, y), scaled_size)
            
            # Draw with maximum quality
            painter.drawPixmap(target_rect, self.collage.grab(), source_rect)
            
            # Draw caption if present
            if self.collage.caption:
                self._render_high_quality_caption(painter, target_rect)
            
            # Get save path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Collage",
                "",
                f"{format.upper()} Files (*.{format})"
            )
            
            if not file_path:
                return
                
            # Ensure correct extension
            if not file_path.lower().endswith(f".{format}"):
                file_path += f".{format}"
            
            # Optimize for format
            final_pixmap = self.optimize_for_format(output_pixmap, format, quality)
            
            # Save with format-specific settings
            success = final_pixmap.save(
                file_path,
                format,
                quality if format != 'png' else -1  # PNG uses lossless compression
            )
            
            if success:
                logging.info(f"Collage saved successfully to {file_path}")
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("Collage saved successfully!")
                msg.setDetailedText(
                    f"Format: {format.upper()}\n"
                    f"Quality: {quality}%\n"
                    f"Resolution: {scale}x\n"
                    f"Size: {output_size.width()}x{output_size.height()}\n"
                    f"Location: {file_path}"
                )
                msg.exec_()
            else:
                raise IOError(f"Failed to save image as {format.upper()}")
                
        except Exception as e:
            self.handle_error("Error saving collage", str(e))

    def get_collage_state(self) -> dict:
        """Get serializable state of the collage."""
        # Convert merged_cells tuple keys to strings for JSON serialization
        merged_cells_serializable = {}
        for (row, col), (row_span, col_span) in self.collage.merged_cells.items():
            key = f"{row},{col}"  # Convert tuple to string
            merged_cells_serializable[key] = [row_span, col_span]
            
        state = {
            'rows': self.collage.rows,
            'columns': self.collage.columns,
            'cell_size': self.collage.cell_size,
            'cells': [],
            'merged_cells': merged_cells_serializable,  # Use serializable format
            'settings': {
                'transform_mode': self.transform_combo.currentIndex(),
                'aspect_mode': self.aspect_combo.currentIndex(),
                'caption_format': {
                    'font_size': self.font_size_spin.value(),
                    'bold': self.bold_checkbox.isChecked(),
                    'italic': self.italic_checkbox.isChecked(),
                    'underline': self.underline_checkbox.isChecked()
                }
            }
        }
        
        # Save cell data
        for cell in self.collage.cells:
            cell_data = {
                'cell_id': cell.cell_id,
                'caption': cell.caption,
                'row_span': cell.row_span,
                'col_span': cell.col_span,
                'selected': cell.selected
            }
            
            # Save image if present
            if cell.pixmap:
                # Save image to temporary file
                temp_path = os.path.join(self.autosave_manager.autosave_path, 
                                       f"img_{cell.cell_id}.png")
                cell.pixmap.save(temp_path, "PNG")
                cell_data['image_path'] = temp_path
                
            state['cells'].append(cell_data)
            
        return state
        
    def restore_collage_state(self, state: dict):
        """Restore collage from saved state."""
        try:
            # Update grid dimensions
            self.rows_spin.setValue(state['rows'])
            self.cols_spin.setValue(state['columns'])
            self.collage.cell_size = state['cell_size']
            
            # Restore settings
            settings = state['settings']
            self.transform_combo.setCurrentIndex(settings['transform_mode'])
            self.aspect_combo.setCurrentIndex(settings['aspect_mode'])
            
            caption_format = settings['caption_format']
            self.font_size_spin.setValue(caption_format['font_size'])
            self.bold_checkbox.setChecked(caption_format['bold'])
            self.italic_checkbox.setChecked(caption_format['italic'])
            self.underline_checkbox.setChecked(caption_format['underline'])
            
            # Create new grid
            self.collage.update_grid(state['rows'], state['columns'])
            
            # Convert string keys back to tuples for merged cells
            self.collage.merged_cells = {}
            for key, (row_span, col_span) in state['merged_cells'].items():
                row, col = map(int, key.split(','))
                self.collage.merged_cells[(row, col)] = (row_span, col_span)
            
            # Apply merges
            for (row, col), (row_span, col_span) in self.collage.merged_cells.items():
                self.collage.merge_cells(row, col, row_span, col_span)
            
            # Restore cell contents
            for cell_data in state['cells']:
                cell_id = cell_data['cell_id']
                for cell in self.collage.cells:
                    if cell.cell_id == cell_id:
                        # Restore image if present
                        if 'image_path' in cell_data:
                            if os.path.exists(cell_data['image_path']):
                                pixmap = QPixmap(cell_data['image_path'])
                                cell.setImage(pixmap)
                        
                        # Restore other properties
                        cell.caption = cell_data['caption']
                        cell.selected = cell_data['selected']
                        cell.row_span = cell_data['row_span']
                        cell.col_span = cell_data['col_span']
                        cell.update()
                        break
            
            logging.info("Collage state restored successfully")
            
        except Exception as e:
            self.handle_error("Failed to restore collage state", str(e))

    def check_for_autosave(self):
        """Check for and offer to restore from autosave."""
        latest_autosave = self.autosave_manager.get_latest_autosave()
        if (latest_autosave):
            try:
                with open(latest_autosave, 'r') as f:
                    state = json.load(f)
                
                # Get autosave timestamp
                timestamp = os.path.basename(latest_autosave).split('_')[2].split('.')[0]
                dt = QDateTime.fromString(timestamp, "yyyyMMddhhmmss")
                time_str = dt.toString("yyyy-MM-dd hh:mm:ss")
                
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Question)
                msg.setText("Autosave Found")
                msg.setInformativeText(f"Would you like to restore the collage from {time_str}?")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                
                if msg.exec() == QMessageBox.Yes:
                    self.restore_collage_state(state)
                    
            except Exception as e:
                self.handle_error("Failed to load autosave", str(e))

# ========================================================
# Punto de Entrada
# ========================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

class ImageQualityManager:
    """Manages image quality settings and optimizations."""
    
    @staticmethod
    def load_high_quality_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)  # Apply EXIF orientation
        reader.setQuality(100)  # Use maximum quality
        
        # Load the image at original quality
        original_image = reader.read()
        if original_image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format while preserving quality
        if original_image.format() != QImage.Format_ARGB32:
            original_image = original_image.convertToFormat(QImage.Format_ARGB32)
        
        # Create high-quality pixmap
        original_pixmap = QPixmap.fromImage(original_image)
        
        return original_pixmap, original_image

class ImageQualityPreserver:
    """Handles consistent high quality image loading and processing."""
    
    @staticmethod
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        try:
            # Configure reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)  # Request maximum quality
            reader.setAllocationLimit(0)  # No memory limits
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap from image
            pixmap = QPixmap.fromImage(original_image)
            
            return pixmap, original_image
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
    
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create high-quality display version of an image."""
        if not original:
            return QPixmap()
            
        # Work at 2x target size for better quality
        intermediate_size = target_size * 2
        
        # Create intermediate high-resolution pixmap
        intermediate = QPixmap(intermediate_size)
        intermediate.fill(Qt.transparent)
        
        # High quality painting
        painter = QPainter(intermediate)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Scale while preserving aspect ratio
        source_rect = original.rect()
        target_rect = QRect(QPoint(0, 0), intermediate_size)
        scaled_rect = source_rect
        
        if original.width() > 0 and original.height() > 0:
            scaled_rect.setSize(source_rect.size().scaled(
                target_rect.size(),
                Qt.KeepAspectRatio
            ))
        
        # Center in target
        scaled_rect.moveCenter(target_rect.center())
        
        # Draw at high resolution
        painter.drawPixmap(scaled_rect, original, source_rect)
        painter.end()
        
        # Scale down to target size with high quality
        return intermediate.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
    
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not pixmap or pixmap.isNull():
                raise ValueError("Invalid pixmap")
                
            format = format.lower()
            if format not in ['png', 'jpg', 'jpeg', 'webp']:
                raise ValueError(f"Unsupported format: {format}")
            
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            original_size = pixmap.size()
            scaled_size = QSize(
                int(original_size.width() * scale_factor),
                int(original_size.height() * scale_factor)
            )
            
            # Create output image with optimal settings
            output_image = QImage(
                scaled_size,
                QImage.Format_ARGB32_Premultiplied
            )
            output_image.fill(Qt.transparent)
            
            # Set high DPI
            output_image.setDotsPerMeterX(int(300 / 0.0254))  # 300 DPI
            output_image.setDotsPerMeterY(int(300 / 0.0254))
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()
            
            # Save with format-specific optimal settings
            if format in ['jpg', 'jpeg']:
                return high_res_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
            elif format == 'webp':
                return high_res_pixmap.save(file_path, format, 100)  # Maximum WebP quality
            else:  # PNG and others
                return high_res_pixmap.save(file_path, format)
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        # Configure reader for maximum quality
        reader.setAutoTransform(True)
        reader.setQuality(100)
        reader.setAllocationLimit(0)  # No memory limits for quality
        
        # Load image at original resolution
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Create lossless pixmap
        pixmap = QPixmap.fromImage(image)
        
        return pixmap, image
        
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create display version while preserving quality."""
        return original.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality settings for each format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB while preserving quality
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve metadata
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image.save(file_path, format, 100)  # Maximum JPEG quality
            else:
                # Already in RGB format
                return pixmap.save(file_path, format, 100)  # Maximum JPEG quality
                
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        
        # PNG doesn't need special handling
        return pixmap

class OutputFormatHandler:
    """Handles output format conversion with quality preservation."""
    
    FORMATS = {
        'png': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.png',
            'mime': 'image/png'
        },
        'jpg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'jpeg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'webp': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.webp',
            'mime': 'image/webp'
        }
    }
    
    def optimize_for_output(self, pixmap: QPixmap, format: str) -> QPixmap:
        """Optimize pixmap for specific output format."""
        format = format.lower()
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        format_info = self.FORMATS[format]
        image = pixmap.toImage()
        
        # Handle alpha channel for non-alpha formats
        if not format_info['alpha_support'] and image.hasAlphaChannel():
            # Create RGB image with white background
            rgb_image = QImage(image.size(), QImage.Format_RGB32)
            rgb_image.fill(Qt.white)
            
            # Use high-quality painter for conversion
            painter = QPainter(rgb_image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Draw original image
            painter.drawImage(0, 0, image)
            painter.end()
            
            return QPixmap.fromImage(rgb_image)
            
        return pixmap
    
    def save_with_optimal_settings(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with optimal quality settings for each format."""
        if not format:
            format = os.path.splitext(file_path)[1][1:].lower()
            
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        # Convert pixmap if needed
        output_pixmap = self.optimize_for_output(pixmap, format)
        
        # Save with format-specific settings
        if format in ['jpg', 'jpeg']:
            return output_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
        elif format == 'webp':
            return output_pixmap.save(file_path, format, 100)  # Maximum WebP quality
        else:  # PNG and other lossless formats
            return output_pixmap.save(file_path, format)

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved with maximum quality to %s", file_path)
            return True
            
        except Exception as e:
            logging.error("Error saving image with quality preservation: %s", e)
            return False

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

class DPIManager:
    """Manages DPI settings and resolution preservation."""
    
    DEFAULT_DPI = 300  # Standard print quality DPI
    
    @staticmethod
    def set_dpi_for_image(image: QImage, dpi: float = DEFAULT_DPI):
        """Set DPI for an image."""
        dpm = dpi / 0.0254  # Convert inches to meters
        image.setDotsPerMeterX(int(dpm))
        image.setDotsPerMeterY(int(dpm))
    
    @staticmethod
    def preserve_dpi(source_image: QImage, target_image: QImage):
        """Copy DPI settings from source to target image."""
        if hasattr(source_image, 'dotsPerMeterX'):
            target_image.setDotsPerMeterX(source_image.dotsPerMeterX())
            target_image.setDotsPerMeterY(source_image.dotsPerMeterY())
    
    @staticmethod
    def create_high_dpi_image(width: int, height: int, format: QImage.Format = QImage.Format_ARGB32_Premultiplied) -> QImage:
        """Create a new image with high DPI settings."""
        image = QImage(width, height, format)
        image.setDotsPerMeterX(int(300 / 0.0254))  # 300 DPI
        image.setDotsPerMeterY(int(300 / 0.0254))
        return image

class ColorSpaceManager:
    """Manages color space transformations with maximum quality preservation."""
    
    COLOR_SPACES = {
        'srgb': QColorSpace.SRgb,
        'display_p3': QColorSpace.DisplayP3,
        'adobe_rgb': QColorSpace.AdobeRgb,
        'pro_photo': QColorSpace.ProPhotoRgb
    }
    
    @staticmethod
    def preserve_color_space(source_image: QImage, target_image: QImage) -> QImage:
        """Preserve color space information when converting images."""
        if source_image.colorSpace().isValid():
            target_image.setColorSpace(source_image.colorSpace())
        else:
            # Default to sRGB if no color space is specified
            target_image.setColorSpace(QColorSpace(QColorSpace.SRgb))
    
    @staticmethod
    def optimize_for_output(image: QImage, output_format: str) -> QImage:
        """Optimize color space for specific output format."""
        if output_format.lower() in ['jpg', 'jpeg']:
            # Convert to sRGB for JPEG
            if not image.colorSpace().isValid() or image.colorSpace().primaries() != QColorSpace.Primaries.SRgb:
                image.convertToColorSpace(QColorSpace(QColorSpace.SRgb))
        
        elif output_format.lower() == 'png':
            # For PNG, preserve original color space if valid
            if not image.colorSpace().isValid():
                image.setColorSpace(QColorSpace(QColorSpace.SRgb))
                
        elif output_format.lower() == 'webp':
            # WebP supports wide color gamut, so preserve original space
            if not image.colorSpace().isValid():
                image.setColorSpace(QColorSpace(QColorSpace.SRgb))
        
        return image
    
    @staticmethod
    def convert_to_format(image: QImage, target_format: QImage.Format,
                         preserve_attributes: bool = True) -> QImage:
        """Convert image to target format while preserving quality."""
        if image.format() == target_format:
            return image
            
        # Create new image with target format
        converted = image.convertToFormat(
            target_format,
            Qt.NoOpaqueDetection
        )
        
        if preserve_attributes:
            # Preserve color space
            ColorSpaceManager.preserve_color_space(image, converted)
            
            # Preserve DPI information
            if hasattr(image, 'dotsPerMeterX'):
                converted.setDotsPerMeterX(image.dotsPerMeterX())
                converted.setDotsPerMeterY(image.dotsPerMeterY())
        
        return converted
    
    @staticmethod
    def ensure_alpha_channel(image: QImage, background: QColor = Qt.white) -> QImage:
        """Ensure image has alpha channel, adding if needed."""
        if not image.hasAlphaChannel():
            # Convert to ARGB32 format
            converted = image.convertToFormat(QImage.Format_ARGB32)
            
            # Create background
            background_image = QImage(
                image.size(),
                QImage.Format_ARGB32
            )
            background_image.fill(background)
            
            # Compose images
            painter = QPainter(background_image)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.drawImage(0, 0, converted)
            painter.end()
            
            return background_image
        
        return image

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved with maximum quality to %s", file_path)
            return True
            
        except Exception as e:
            logging.error("Error saving image with quality preservation: %s", e)
            return False

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

class ImageQualityManager:
    """Manages image quality settings and optimizations."""
    
    @staticmethod
    def load_high_quality_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)  # Apply EXIF orientation
        reader.setQuality(100)  # Use maximum quality
        
        # Load the image at original quality
        original_image = reader.read()
        if original_image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format while preserving quality
        if original_image.format() != QImage.Format_ARGB32:
            original_image = original_image.convertToFormat(QImage.Format_ARGB32)
        
        # Create high-quality pixmap
        original_pixmap = QPixmap.fromImage(original_image)
        
        return original_pixmap, original_image

class ImageQualityPreserver:
    """Handles consistent high quality image loading and processing."""
    
    @staticmethod
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        # Configure reader for maximum quality
        reader.setAutoTransform(True)
        reader.setQuality(100)
        reader.setAllocationLimit(0)  # No memory limits for quality
        
        # Load image at original resolution
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Create lossless pixmap
        pixmap = QPixmap.fromImage(image)
        
        return pixmap, image
        
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create display version while preserving quality."""
        return original.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality settings for each format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB while preserving quality
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve metadata
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image.save(file_path, format, 100)  # Maximum JPEG quality
            else:
                # Already in RGB format
                return pixmap.save(file_path, format, 100)  # Maximum JPEG quality
                
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        
        # PNG doesn't need special handling
        return pixmap

class OutputFormatHandler:
    """Handles output format conversion with quality preservation."""
    
    FORMATS = {
        'png': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.png',
            'mime': 'image/png'
        },
        'jpg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'jpeg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'webp': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.webp',
            'mime': 'image/webp'
        }
    }
    
    def optimize_for_output(self, pixmap: QPixmap, format: str) -> QPixmap:
        """Optimize pixmap for specific output format."""
        format = format.lower()
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        format_info = self.FORMATS[format]
        image = pixmap.toImage()
        
        # Handle alpha channel for non-alpha formats
        if not format_info['alpha_support'] and image.hasAlphaChannel():
            # Create RGB image with white background
            rgb_image = QImage(image.size(), QImage.Format_RGB32)
            rgb_image.fill(Qt.white)
            
            # Use high-quality painter for conversion
            painter = QPainter(rgb_image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Draw original image
            painter.drawImage(0, 0, image)
            painter.end()
            
            return QPixmap.fromImage(rgb_image)
            
        return pixmap
    
    def save_with_optimal_settings(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with optimal quality settings for each format."""
        if not format:
            format = os.path.splitext(file_path)[1][1:].lower()
            
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        # Convert pixmap if needed
        output_pixmap = self.optimize_for_output(pixmap, format)
        
        # Save with format-specific settings
        if format in ['jpg', 'jpeg']:
            return output_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
        elif format == 'webp':
            return output_pixmap.save(file_path, format, 100)  # Maximum WebP quality
        else:  # PNG and other lossless formats
            return output_pixmap.save(file_path, format)

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved with maximum quality to %s", file_path)
            return True
            
        except Exception as e:
            logging.error("Error saving image with quality preservation: %s", e)
            return False

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

class ImageQualityManager:
    """Manages image quality settings and optimizations."""
    
    @staticmethod
    def load_high_quality_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)  # Apply EXIF orientation
        reader.setQuality(100)  # Use maximum quality
        
        # Load the image at original quality
        original_image = reader.read()
        if original_image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format while preserving quality
        if original_image.format() != QImage.Format_ARGB32:
            original_image = original_image.convertToFormat(QImage.Format_ARGB32)
        
        # Create high-quality pixmap
        original_pixmap = QPixmap.fromImage(original_image)
        
        return original_pixmap, original_image

class ImageQualityPreserver:
    """Handles consistent high quality image loading and processing."""
    
    @staticmethod
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        # Configure reader for maximum quality
        reader.setAutoTransform(True)
        reader.setQuality(100)
        reader.setAllocationLimit(0)  # No memory limits for quality
        
        # Load image at original resolution
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Create lossless pixmap
        pixmap = QPixmap.fromImage(image)
        
        return pixmap, image
        
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create display version while preserving quality."""
        return original.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality settings for each format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB while preserving quality
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve metadata
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image.save(file_path, format, 100)  # Maximum JPEG quality
            else:
                # Already in RGB format
                return pixmap.save(file_path, format, 100)  # Maximum JPEG quality
                
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        
        # PNG doesn't need special handling
        return pixmap

class OutputFormatHandler:
    """Handles output format conversion with quality preservation."""
    
    FORMATS = {
        'png': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.png',
            'mime': 'image/png'
        },
        'jpg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'jpeg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'webp': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.webp',
            'mime': 'image/webp'
        }
    }
    
    def optimize_for_output(self, pixmap: QPixmap, format: str) -> QPixmap:
        """Optimize pixmap for specific output format."""
        format = format.lower()
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        format_info = self.FORMATS[format]
        image = pixmap.toImage()
        
        # Handle alpha channel for non-alpha formats
        if not format_info['alpha_support'] and image.hasAlphaChannel():
            # Create RGB image with white background
            rgb_image = QImage(image.size(), QImage.Format_RGB32)
            rgb_image.fill(Qt.white)
            
            # Use high-quality painter for conversion
            painter = QPainter(rgb_image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Draw original image
            painter.drawImage(0, 0, image)
            painter.end()
            
            return QPixmap.fromImage(rgb_image)
            
        return pixmap
    
    def save_with_optimal_settings(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with optimal quality settings for each format."""
        if not format:
            format = os.path.splitext(file_path)[1][1:].lower()
            
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        # Convert pixmap if needed
        output_pixmap = self.optimize_for_output(pixmap, format)
        
        # Save with format-specific settings
        if format in ['jpg', 'jpeg']:
            return output_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
        elif format == 'webp':
            return output_pixmap.save(file_path, format, 100)  # Maximum WebP quality
        else:  # PNG and other lossless formats
            return output_pixmap.save(file_path, format)

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved with maximum quality to %s", file_path)
            return True
            
        except Exception as e:
            logging.error("Error saving image with quality preservation: %s", e)
            return False

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

class ImageQualityManager:
    """Manages image quality settings and optimizations."""
    
    @staticmethod
    def load_high_quality_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)  # Apply EXIF orientation
        reader.setQuality(100)  # Use maximum quality
        
        # Load the image at original quality
        original_image = reader.read()
        if original_image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format while preserving quality
        if original_image.format() != QImage.Format_ARGB32:
            original_image = original_image.convertToFormat(QImage.Format_ARGB32)
        
        # Create high-quality pixmap
        original_pixmap = QPixmap.fromImage(original_image)
        
        return original_pixmap, original_image

class ImageQualityPreserver:
    """Handles consistent high quality image loading and processing."""
    
    @staticmethod
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        # Configure reader for maximum quality
        reader.setAutoTransform(True)
        reader.setQuality(100)
        reader.setAllocationLimit(0)  # No memory limits for quality
        
        # Load image at original resolution
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Create lossless pixmap
        pixmap = QPixmap.fromImage(image)
        
        return pixmap, image
        
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create display version while preserving quality."""
        return original.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality settings for each format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB while preserving quality
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve metadata
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image.save(file_path, format, 100)  # Maximum JPEG quality
            else:
                # Already in RGB format
                return pixmap.save(file_path, format, 100)  # Maximum JPEG quality
                
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        
        # PNG doesn't need special handling
        return pixmap

class OutputFormatHandler:
    """Handles output format conversion with quality preservation."""
    
    FORMATS = {
        'png': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.png',
            'mime': 'image/png'
        },
        'jpg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'jpeg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'webp': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.webp',
            'mime': 'image/webp'
        }
    }
    
    def optimize_for_output(self, pixmap: QPixmap, format: str) -> QPixmap:
        """Optimize pixmap for specific output format."""
        format = format.lower()
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        format_info = self.FORMATS[format]
        image = pixmap.toImage()
        
        # Handle alpha channel for non-alpha formats
        if not format_info['alpha_support'] and image.hasAlphaChannel():
            # Create RGB image with white background
            rgb_image = QImage(image.size(), QImage.Format_RGB32)
            rgb_image.fill(Qt.white)
            
            # Use high-quality painter for conversion
            painter = QPainter(rgb_image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Draw original image
            painter.drawImage(0, 0, image)
            painter.end()
            
            return QPixmap.fromImage(rgb_image)
            
        return pixmap
    
    def save_with_optimal_settings(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with optimal quality settings for each format."""
        if not format:
            format = os.path.splitext(file_path)[1][1:].lower()
            
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        # Convert pixmap if needed
        output_pixmap = self.optimize_for_output(pixmap, format)
        
        # Save with format-specific settings
        if format in ['jpg', 'jpeg']:
            return output_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
        elif format == 'webp':
            return output_pixmap.save(file_path, format, 100)  # Maximum WebP quality
        else:  # PNG and other lossless formats
            return output_pixmap.save(file_path, format)

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved with maximum quality to %s", file_path)
            return True
            
        except Exception as e:
            logging.error("Error saving image with quality preservation: %s", e)
            return False

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

class ImageQualityManager:
    """Manages image quality settings and optimizations."""
    
    @staticmethod
    def load_high_quality_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)  # Apply EXIF orientation
        reader.setQuality(100)  # Use maximum quality
        
        # Load the image at original quality
        original_image = reader.read()
        if original_image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format while preserving quality
        if original_image.format() != QImage.Format_ARGB32:
            original_image = original_image.convertToFormat(QImage.Format_ARGB32)
        
        # Create high-quality pixmap
        original_pixmap = QPixmap.fromImage(original_image)
        
        return original_pixmap, original_image

class ImageQualityPreserver:
    """Handles consistent high quality image loading and processing."""
    
    @staticmethod
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        # Configure reader for maximum quality
        reader.setAutoTransform(True)
        reader.setQuality(100)
        reader.setAllocationLimit(0)  # No memory limits for quality
        
        # Load image at original resolution
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Create lossless pixmap
        pixmap = QPixmap.fromImage(image)
        
        return pixmap, image
        
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create display version while preserving quality."""
        return original.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality settings for each format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB while preserving quality
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve metadata
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image.save(file_path, format, 100)  # Maximum JPEG quality
            else:
                # Already in RGB format
                return pixmap.save(file_path, format, 100)  # Maximum JPEG quality
                
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        
        # PNG doesn't need special handling
        return pixmap

class OutputFormatHandler:
    """Handles output format conversion with quality preservation."""
    
    FORMATS = {
        'png': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.png',
            'mime': 'image/png'
        },
        'jpg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'jpeg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'webp': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.webp',
            'mime': 'image/webp'
        }
    }
    
    def optimize_for_output(self, pixmap: QPixmap, format: str) -> QPixmap:
        """Optimize pixmap for specific output format."""
        format = format.lower()
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        format_info = self.FORMATS[format]
        image = pixmap.toImage()
        
        # Handle alpha channel for non-alpha formats
        if not format_info['alpha_support'] and image.hasAlphaChannel():
            # Create RGB image with white background
            rgb_image = QImage(image.size(), QImage.Format_RGB32)
            rgb_image.fill(Qt.white)
            
            # Use high-quality painter for conversion
            painter = QPainter(rgb_image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Draw original image
            painter.drawImage(0, 0, image)
            painter.end()
            
            return QPixmap.fromImage(rgb_image)
            
        return pixmap
    
    def save_with_optimal_settings(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with optimal quality settings for each format."""
        if not format:
            format = os.path.splitext(file_path)[1][1:].lower()
            
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        # Convert pixmap if needed
        output_pixmap = self.optimize_for_output(pixmap, format)
        
        # Save with format-specific settings
        if format in ['jpg', 'jpeg']:
            return output_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
        elif format == 'webp':
            return output_pixmap.save(file_path, format, 100)  # Maximum WebP quality
        else:  # PNG and other lossless formats
            return output_pixmap.save(file_path, format)

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved with maximum quality to %s", file_path)
            return True
            
        except Exception as e:
            logging.error("Error saving image with quality preservation: %s", e)
            return False

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

class ImageQualityManager:
    """Manages image quality settings and optimizations."""
    
    @staticmethod
    def load_high_quality_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)  # Apply EXIF orientation
        reader.setQuality(100)  # Use maximum quality
        
        # Load the image at original quality
        original_image = reader.read()
        if original_image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format while preserving quality
        if original_image.format() != QImage.Format_ARGB32:
            original_image = original_image.convertToFormat(QImage.Format_ARGB32)
        
        # Create high-quality pixmap
        original_pixmap = QPixmap.fromImage(original_image)
        
        return original_pixmap, original_image

class ImageQualityPreserver:
    """Handles consistent high quality image loading and processing."""
    
    @staticmethod
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        # Configure reader for maximum quality
        reader.setAutoTransform(True)
        reader.setQuality(100)
        reader.setAllocationLimit(0)  # No memory limits for quality
        
        # Load image at original resolution
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Create lossless pixmap
        pixmap = QPixmap.fromImage(image)
        
        return pixmap, image
        
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create display version while preserving quality."""
        return original.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality settings for each format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB while preserving quality
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve metadata
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image.save(file_path, format, 100)  # Maximum JPEG quality
            else:
                # Already in RGB format
                return pixmap.save(file_path, format, 100)  # Maximum JPEG quality
                
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        
        # PNG doesn't need special handling
        return pixmap

class OutputFormatHandler:
    """Handles output format conversion with quality preservation."""
    
    FORMATS = {
        'png': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.png',
            'mime': 'image/png'
        },
        'jpg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'jpeg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'webp': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.webp',
            'mime': 'image/webp'
        }
    }
    
    def optimize_for_output(self, pixmap: QPixmap, format: str) -> QPixmap:
        """Optimize pixmap for specific output format."""
        format = format.lower()
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        format_info = self.FORMATS[format]
        image = pixmap.toImage()
        
        # Handle alpha channel for non-alpha formats
        if not format_info['alpha_support'] and image.hasAlphaChannel():
            # Create RGB image with white background
            rgb_image = QImage(image.size(), QImage.Format_RGB32)
            rgb_image.fill(Qt.white)
            
            # Use high-quality painter for conversion
            painter = QPainter(rgb_image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Draw original image
            painter.drawImage(0, 0, image)
            painter.end()
            
            return QPixmap.fromImage(rgb_image)
            
        return pixmap
    
    def save_with_optimal_settings(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with optimal quality settings for each format."""
        if not format:
            format = os.path.splitext(file_path)[1][1:].lower()
            
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        # Convert pixmap if needed
        output_pixmap = self.optimize_for_output(pixmap, format)
        
        # Save with format-specific settings
        if format in ['jpg', 'jpeg']:
            return output_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
        elif format == 'webp':
            return output_pixmap.save(file_path, format, 100)  # Maximum WebP quality
        else:  # PNG and other lossless formats
            return output_pixmap.save(file_path, format)

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved with maximum quality to %s", file_path)
            return True
            
        except Exception as e:
            logging.error("Error saving image with quality preservation: %s", e)
            return False

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

class ImageQualityManager:
    """Manages image quality settings and optimizations."""
    
    @staticmethod
    def load_high_quality_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)  # Apply EXIF orientation
        reader.setQuality(100)  # Use maximum quality
        
        # Load the image at original quality
        original_image = reader.read()
        if original_image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format while preserving quality
        if original_image.format() != QImage.Format_ARGB32:
            original_image = original_image.convertToFormat(QImage.Format_ARGB32)
        
        # Create high-quality pixmap
        original_pixmap = QPixmap.fromImage(original_image)
        
        return original_pixmap, original_image

class ImageQualityPreserver:
    """Handles consistent high quality image loading and processing."""
    
    @staticmethod
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        # Configure reader for maximum quality
        reader.setAutoTransform(True)
        reader.setQuality(100)
        reader.setAllocationLimit(0)  # No memory limits for quality
        
        # Load image at original resolution
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Create lossless pixmap
        pixmap = QPixmap.fromImage(image)
        
        return pixmap, image
        
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create display version while preserving quality."""
        return original.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality settings for each format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB while preserving quality
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve metadata
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image.save(file_path, format, 100)  # Maximum JPEG quality
            else:
                # Already in RGB format
                return pixmap.save(file_path, format, 100)  # Maximum JPEG quality
                
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        
        # PNG doesn't need special handling
        return pixmap

class OutputFormatHandler:
    """Handles output format conversion with quality preservation."""
    
    FORMATS = {
        'png': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.png',
            'mime': 'image/png'
        },
        'jpg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'jpeg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'webp': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.webp',
            'mime': 'image/webp'
        }
    }
    
    def optimize_for_output(self, pixmap: QPixmap, format: str) -> QPixmap:
        """Optimize pixmap for specific output format."""
        format = format.lower()
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        format_info = self.FORMATS[format]
        image = pixmap.toImage()
        
        # Handle alpha channel for non-alpha formats
        if not format_info['alpha_support'] and image.hasAlphaChannel():
            # Create RGB image with white background
            rgb_image = QImage(image.size(), QImage.Format_RGB32)
            rgb_image.fill(Qt.white)
            
            # Use high-quality painter for conversion
            painter = QPainter(rgb_image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Draw original image
            painter.drawImage(0, 0, image)
            painter.end()
            
            return QPixmap.fromImage(rgb_image)
            
        return pixmap
    
    def save_with_optimal_settings(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with optimal quality settings for each format."""
        if not format:
            format = os.path.splitext(file_path)[1][1:].lower()
            
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        # Convert pixmap if needed
        output_pixmap = self.optimize_for_output(pixmap, format)
        
        # Save with format-specific settings
        if format in ['jpg', 'jpeg']:
            return output_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
        elif format == 'webp':
            return output_pixmap.save(file_path, format, 100)  # Maximum WebP quality
        else:  # PNG and other lossless formats
            return output_pixmap.save(file_path, format)

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved with maximum quality to %s", file_path)
            return True
            
        except Exception as e:
            logging.error("Error saving image with quality preservation: %s", e)
            return False

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

class ImageQualityManager:
    """Manages image quality settings and optimizations."""
    
    @staticmethod
    def load_high_quality_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)  # Apply EXIF orientation
        reader.setQuality(100)  # Use maximum quality
        
        # Load the image at original quality
        original_image = reader.read()
        if original_image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format while preserving quality
        if original_image.format() != QImage.Format_ARGB32:
            original_image = original_image.convertToFormat(QImage.Format_ARGB32)
        
        # Create high-quality pixmap
        original_pixmap = QPixmap.fromImage(original_image)
        
        return original_pixmap, original_image

class ImageQualityPreserver:
    """Handles consistent high quality image loading and processing."""
    
    @staticmethod
    def load_image(file_path: str) -> tuple[QPixmap, QImage]:
        """Load image with maximum quality preservation."""
        reader = QImageReader(file_path)
        # Configure reader for maximum quality
        reader.setAutoTransform(True)
        reader.setQuality(100)
        reader.setAllocationLimit(0)  # No memory limits for quality
        
        # Load image at original resolution
        image = reader.read()
        if image.isNull():
            raise ValueError(f"Failed to load image: {reader.errorString()}")
        
        # Convert to optimal format for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Create lossless pixmap
        pixmap = QPixmap.fromImage(image)
        
        return pixmap, image
        
    @staticmethod
    def create_display_version(original: QPixmap, target_size: QSize) -> QPixmap:
        """Create display version while preserving quality."""
        return original.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
    @staticmethod
    def save_with_quality(pixmap: QPixmap, file_path: str, format: str) -> bool:
        """Save image with maximum quality settings for each format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB while preserving quality
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                # Create RGB image with white background
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve metadata
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image.save(file_path, format, 100)  # Maximum JPEG quality
            else:
                # Already in RGB format
                return pixmap.save(file_path, format, 100)  # Maximum JPEG quality
                
        elif format == 'webp':
            # WebP supports transparency and compression
            return pixmap
        
        # PNG doesn't need special handling
        return pixmap

class OutputFormatHandler:
    """Handles output format conversion with quality preservation."""
    
    FORMATS = {
        'png': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.png',
            'mime': 'image/png'
        },
        'jpg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'jpeg': {
            'lossless': False,
            'alpha_support': False,
            'extension': '.jpg',
            'mime': 'image/jpeg'
        },
        'webp': {
            'lossless': True,
            'alpha_support': True,
            'extension': '.webp',
            'mime': 'image/webp'
        }
    }
    
    def optimize_for_output(self, pixmap: QPixmap, format: str) -> QPixmap:
        """Optimize pixmap for specific output format."""
        format = format.lower()
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        format_info = self.FORMATS[format]
        image = pixmap.toImage()
        
        # Handle alpha channel for non-alpha formats
        if not format_info['alpha_support'] and image.hasAlphaChannel():
            # Create RGB image with white background
            rgb_image = QImage(image.size(), QImage.Format_RGB32)
            rgb_image.fill(Qt.white)
            
            # Use high-quality painter for conversion
            painter = QPainter(rgb_image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Draw original image
            painter.drawImage(0, 0, image)
            painter.end()
            
            return QPixmap.fromImage(rgb_image)
            
        return pixmap
    
    def save_with_optimal_settings(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with optimal quality settings for each format."""
        if not format:
            format = os.path.splitext(file_path)[1][1:].lower()
            
        if format not in self.FORMATS:
            raise ValueError(f"Unsupported format: {format}")
            
        # Convert pixmap if needed
        output_pixmap = self.optimize_for_output(pixmap, format)
        
        # Save with format-specific settings
        if format in ['jpg', 'jpeg']:
            return output_pixmap.save(file_path, format, 100)  # Maximum JPEG quality
        elif format == 'webp':
            return output_pixmap.save(file_path, format, 100)  # Maximum WebP quality
        else:  # PNG and other lossless formats
            return output_pixmap.save(file_path, format)

class QualitySettingsManager:
    """Manages quality settings across the application."""
    
    DEFAULT_SETTINGS = {
        'image': {
            'dpi': 300,  # Default DPI for high quality
            'scale_factor': 4.0,  # Default scale factor for saving
            'transformation': Qt.SmoothTransformation,
            'color_space': QImage.Format_ARGB32_Premultiplied
        },
        'output': {
            'png': {
                'compression': 0,  # No compression for maximum quality
                'gamma': 2.2  # Standard gamma correction
            },
            'jpeg': {
                'quality': 100,  # Maximum quality
                'optimize': False,  # No optimization to preserve quality
                'progressive': False  # No progressive to maintain quality
            },
            'webp': {
                'quality': 100,  # Maximum quality
                'lossless': True,  # Use lossless compression
                'method': 6  # Highest quality compression method
            }
        },
        'processing': {
            'intermediate_scale': 2.0,  # Scale factor for intermediate processing
            'preserve_metadata': True,
            'preserve_color_profile': True,
            'preserve_dpi': True
        }
    }
    
    def __init__(self):
        self.settings = self.DEFAULT_SETTINGS.copy()
        
    def get_save_options(self, format: str) -> dict:
        """Get optimal save options for format."""
        return self.settings['output'].get(format.lower(), {})

class QualityPreservationInterface:
    """Central interface for coordinating all quality preservation systems."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        self.memory_manager = MemoryProfileManager()
        
    def load_image(self, file_path: str) -> tuple[QPixmap, dict]:
        """Load image with maximum quality preservation."""
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            reader.setQuality(100)
            reader.setAllocationLimit(0)
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise IOError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32_Premultiplied:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
            
            # Create high-quality pixmap preserving all attributes
            high_quality_pixmap = QPixmap.fromImage(original_image)
            
            # Collect metadata
            metadata = {
                'size': original_image.size(),
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'color_space': original_image.colorSpace(),
                'has_alpha': original_image.hasAlphaChannel(),
                'depth': original_image.depth()
            }
            
            return high_quality_pixmap, metadata
            
        except Exception as e:
            logging.error(f"Error loading image with quality preservation: {str(e)}")
            raise
            
    def save_image(self, pixmap: QPixmap, file_path: str, format: str = None) -> bool:
        """Save image with maximum quality preservation."""
        try:
            if not format:
                format = os.path.splitext(file_path)[1][1:].lower()
            
            # Get optimal settings for format
            settings = self.quality_manager.get_save_options(format)
            
            # Create high-resolution output with 4x scale
            scale_factor = settings['image']['scale_factor']
            original_size = pixmap.size()
            scaled_size = QSize(int(original_size.width() * scale_factor), 
                              int(original_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, settings['image']['color_space'])
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            
            # Optimize for output format
            output_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(output_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

# ========================================================
# Worker, TaskQueue, and related classes
# ========================================================

class WorkerSignals(QObject):
    """Defines signals for worker threads."""
    started = Signal()
    finished = Signal()
    error = Signal(str)
    progress = Signal(int)
    result = Signal(object)

class Worker(QRunnable):
    """Base worker class for background tasks."""
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
    def run(self):
        """Execute the task."""
        try:
            self.signals.started.emit()
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

class TaskQueue:
    """Manages queued tasks with priority handling."""
    def __init__(self, max_concurrent=4):
        self.queue = []
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(max_concurrent)
        self.mutex = QMutex()
        self.processing = False

    def add_task(self, task, priority=0):
        """Add a task to the queue with optional priority."""
        with QMutexLocker(self.mutex):
            self.queue.append((priority, task))
            self.queue.sort(key=lambda x: x[0], reverse=True)
            
        if not self.processing:
            self.process_next()

    def process_next(self):
        """Process the next task in the queue."""
        with QMutexLocker(self.mutex):
            if not self.queue:
                self.processing = False
                return
                
            self.processing = True
            _, task = self.queue.pop(0)
            
        self.thread_pool.start(task)
        task.signals.finished.connect(self.process_next)

    def clear(self):
        """Clear all pending tasks."""
        with QMutexLocker(self.mutex):
            self.queue.clear()

    def is_empty(self):
        """Check if queue is empty."""
        with QMutexLocker(self.mutex):
            return len(self.queue) == 0

class ImageLoadWorker(QThread):
    """Worker thread for loading and processing images with maximum quality preservation."""
    finished = Signal(QPixmap, str)  # Emits processed pixmap and filename
    error = Signal(str)  # Emits error message if loading fails
    progress = Signal(int)  # Emits progress percentage
    
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._cancelled = False
        
    def run(self):
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(self.file_path)
            reader.setAutoTransform(True)  # Apply EXIF orientation
            reader.setQuality(100)  # Maximum quality
            reader.setAllocationLimit(0)  # No memory limits for better quality
            
            # Get image info before loading
            original_size = reader.size()
            if not original_size.isValid():
                self.error.emit(f"Invalid image size: {reader.errorString()}")
                return
                
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                self.error.emit(f"Failed to load image: {reader.errorString()}")
                return
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32,
                    Qt.NoOpaqueDetection  # Preserve alpha channel quality
                )
                # Restore original DPI
                original_image.setDotsPerMeterX(dpmX)
                original_image.setDotsPerMeterY(dpmY)
            
            # Create high-quality pixmap preserving all attributes
            self.original_pixmap = QPixmap.fromImage(original_image)
            self.original_image = original_image  # Keep original for quality preservation
            
            # Create optimized display version
            display_size = self.size()
            if original_size.width() > display_size.width() * 3 or original_size.height() > display_size.height() * 3:
                # Scale down for display while maintaining quality
                self.pixmap = self.original_pixmap.scaled(
                    display_size * 2,  # Keep 2x resolution for quality
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            else:
                # Use original size if not too large
                self.pixmap = self.original_pixmap.copy()
            
            # Cache the original high-quality version
            metadata = {
                'size': original_size,
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'timestamp': QFileInfo(self.file_path).lastModified()
            }
            image_cache.put(self.file_path, self.original_pixmap, metadata)
            
            self.update()
            self.finished.emit(self.pixmap, self.file_path)
            logging.info(f"Successfully loaded high-quality image in cell {self.cell_id}")
            
        except Exception as e:
            self.error.emit(str(e))
            
    def cancel(self):
        self._cancelled = True

class BatchProcessor:
    """Handles batch processing of multiple images."""
    def __init__(self, parent):
        self.parent = parent
        self.processing_queue = []
        self.current_worker = None
        
    def process_files(self, file_paths: list, target_size: QSize = None):
        """Start batch processing of files."""
        self.processing_queue = file_paths
        
        # Create and configure progress dialog
        progress = QProgressDialog("Processing images...", "Cancel", 0, len(file_paths), self.parent)
        progress.setWindowModality(Qt.WindowModal)
        
        # Create worker thread
        self.current_worker = ImageLoadWorker(file_paths, target_size)
        
        # Connect signals
        self.current_worker.finished.connect(self._on_image_processed)
        self.current_worker.error.connect(self._on_error)
        self.current_worker.progress.connect(progress.setValue)
        progress.canceled.connect(self.current_worker.cancel)
        
        # Start processing
        self.current_worker.start()
        progress.exec_()
        
    def _on_image_processed(self, pixmap: QPixmap, file_path: str):
        """Handle processed image."""
        # Add to cache
        metadata = ImageOptimizer.process_metadata(file_path)
        image_cache.put(file_path, pixmap, metadata)
        
    def _on_error(self, error_message: str):
        """Handle processing error."""
        QMessageBox.warning(
            self.parent,
            "Processing Error",
            error_message
        )

class AutosaveManager:
    """Manages automatic saving of collage state."""
    def __init__(self, parent):
        self.parent = parent
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self.perform_autosave)
        self.autosave_interval = 5 * 60 * 1000  # 5 minutes in milliseconds
        self.autosave_path = "autosave"
        self.ensure_autosave_dir()
        
    def ensure_autosave_dir(self):
        """Ensure autosave directory exists."""
        if not os.path.exists(self.autosave_path):
            os.makedirs(self.autosave_path)
            
    def start(self):
        """Start autosave timer."""
        self.autosave_timer.start(self.autosave_interval)
        
    def stop(self):
        """Stop autosave timer."""
        self.autosave_timer.stop()
        
    def perform_autosave(self):
        """Perform the autosave operation."""
        try:
            # Generate autosave filename with timestamp
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
            filename = f"collage_autosave_{timestamp}.json"
            filepath = os.path.join(self.autosave_path, filename)
            
            # Get collage state
            state = self.parent.get_collage_state()
            
            # Save state to file
            with open(filepath, 'w') as f:
                json.dump(state, f)
                
            # Clean up old autosaves (keep last 5)
            self.cleanup_old_autosaves()
            
            logging.info(f"Autosave completed: {filepath}")
            
        except Exception as e:
            logging.error(f"Autosave failed: {str(e)}")
            
    def cleanup_old_autosaves(self):
        """Keep only the 5 most recent autosaves."""
        try:
            files = glob.glob(os.path.join(self.autosave_path, "collage_autosave_*.json"))
            files.sort(reverse=True)
            
            # Remove old files
            for old_file in files[5:]:
                try:
                    os.remove(old_file)
                except:
                    pass
                    
        except Exception as e:
            logging.error(f"Autosave cleanup failed: {str(e)}")
            
    def get_latest_autosave(self):
        """Get the most recent autosave file."""
        try:
            files = glob.glob(os.path.join(self.autosave_path, "collage_autosave_*.json"))
            if files:
                return max(files, key=os.path.getctime)
        except Exception as e:
            logging.error(f"Failed to get latest autosave: {str(e)}")
        return None

class PerformanceMonitor:
    """Monitors and optimizes application performance."""
    def __init__(self):
        self.memory_threshold = 500 * 1024 * 1024  # 500MB
        self.last_cleanup = QDateTime.currentDateTime()
        self.cleanup_interval = 300  # 5 minutes in seconds
        
    def check_memory_usage(self):
        """Check current memory usage and optimize if needed."""
        try:
            if HAS_PSUTIL:
                process = psutil.Process()
                memory_info = process.memory_info()
                
                if memory_info.rss > self.memory_threshold:
                    current_time = QDateTime.currentDateTime()
                    if self.last_cleanup.secsTo(current_time) >= self.cleanup_interval:
                        self.optimize_memory_usage()
                        self.last_cleanup = current_time
                    
        except Exception as e:
            logging.warning(f"Memory monitoring error: {str(e)}")
            
    def optimize_memory_usage(self):
        """Perform memory optimization."""
        # Clear image cache if too large
        if len(image_cache.cache) > image_cache.max_size * 0.8:
            image_cache._cleanup()
            
        # Force Python garbage collection
        gc.collect()
        
        logging.info("Memory optimization performed")

class ErrorHandlingManager:
    """Manages error handling and recovery for image operations."""
    
    class ImageOperationError(Exception):
        """Base exception for image operations."""
        pass
        
    class LoadError(ImageOperationError):
        """Error loading an image."""
        pass
        
    class SaveError(ImageOperationError):
        """Error saving an image."""
        pass
        
    class FormatError(ImageOperationError):
        """Error with image format."""
        pass
        
    class MemoryError(ImageOperationError):
        """Error with memory allocation."""
        pass
    
    def __init__(self):
        self.error_handlers = {
            'load': self._handle_load_error,
            'save': self._handle_save_error,
            'format': self._handle_format_error,
            'memory': self._handle_memory_error
        }
        
    def handle_error(self, operation: str, error: Exception, context: dict = None) -> bool:
        """Handle an error during image operations."""
        try:
            if operation in self.error_handlers:
                return self.error_handlers[operation](error, context or {})
            return self._handle_unknown_error(error, context or {})
        except Exception as e:
            logging.error(f"Error in error handler: {str(e)}")
            return False
            
    def _handle_load_error(self, error: Exception, context: dict) -> bool:
        """Handle image loading errors."""
        file_path = context.get('file_path', 'unknown')
        error_msg = str(error)
        
        if 'Permission denied' in error_msg:
            logging.error(f"Permission denied accessing {file_path}")
            return False
            
        if 'No such file' in error_msg:
            logging.error(f"File not found: {file_path}")
            return False
            
        if 'Invalid format' in error_msg:
            logging.error(f"Invalid image format: {file_path}")
            return False
            
        logging.error(f"Unknown error loading image {file_path}: {error_msg}")
        return False
        
    def _handle_save_error(self, error: Exception, context: dict) -> bool:
        """Handle image saving errors."""
        file_path = context.get('file_path', 'unknown')
        format = context.get('format', 'unknown')
        
        if isinstance(error, IOError):
            if 'Permission denied' in str(error):
                logging.error(f"Permission denied saving to {file_path}")
                return False
                
            if 'No space' in str(error):
                logging.error(f"No disk space available saving to {file_path}")
                return False
                
        if isinstance(error, ValueError):
            if 'format' in str(error).lower():
                logging.error(f"Unsupported format {format} for {file_path}")
                return False
                
        logging.error(f"Unknown error saving image {file_path}: {str(error)}")
        return False
        
    def _handle_format_error(self, error: Exception, context: dict) -> bool:
        """Handle format conversion errors."""
        source_format = context.get('source_format', 'unknown')
        target_format = context.get('target_format', 'unknown')
        
        if 'Unsupported conversion' in str(error):
            logging.error(f"Unsupported conversion from {source_format} to {target_format}")
            return False
            
        if 'Invalid format' in str(error):
            logging.error(f"Invalid format specified: {target_format}")
            return False
            
        logging.error(f"Unknown format error converting {source_format} to {target_format}: {str(error)}")
        return False
        
    def _handle_memory_error(self, error: Exception, context: dict) -> bool:
        """Handle memory-related errors."""
        operation = context.get('operation', 'unknown')
        size = context.get('size', 'unknown')
        
        if isinstance(error, MemoryError):
            logging.error(f"Memory allocation failed for {operation} (size: {size})")
            return False
            
        logging.error(f"Unknown memory error during {operation}: {str(error)}")
        return False
        
    def _handle_unknown_error(self, error: Exception, context: dict) -> bool:
        """Handle unknown errors."""
        operation = context.get('operation', 'unknown')
        logging.error(f"Unknown error during {operation}: {str(error)}")
        return False

# ========================================================
# Ventana Principal
# ========================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker - PySide6")
        self.resize(850, 650)
        
        # Initialize undo stack
        self.undo_stack = UndoStack()
        
        # Create keyboard shortcuts
        self.create_shortcuts()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.addLayout(self.create_controls_panel())
        self.collage = CollageWidget(rows=self.rows_spin.value(), columns=self.cols_spin.value(), cell_size=260)
        main_layout.addWidget(self.collage, alignment=Qt.AlignCenter)
        logging.info("Ventana principal inicializada.")
        
        # Initialize autosave manager
        self.autosave_manager = AutosaveManager(self)
        self.autosave_manager.start()
        
        # Check for autosave
        self.check_for_autosave()
        self.batch_processor = BatchProcessor(self)
        
        # Initialize performance monitor
        self.performance_monitor = PerformanceMonitor()
        
        # Initialize error recovery manager
        self.error_recovery_manager = ErrorRecoveryManager(self)
        
        # Initialize save manager
        self.save_manager = SaveManager()
        
    def handle_batch_import(self):
        """Handle batch import of multiple images."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
        )
        
        if file_paths:
            # Calculate target size based on cell dimensions
            target_size = QSize(
                self.collage.cell_size * 2,  # 2x cell size for high quality
                self.collage.cell_size * 2
            )
            
            # Start batch processing
            self.batch_processor.process_files(file_paths, target_size)
            
    def create_shortcuts(self):
        """Create keyboard shortcuts for common actions."""
        # Undo/Redo shortcuts
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self.undo_action)
        
        redo_shortcut = QShortcut(QKeySequence.Redo, self)
        redo_shortcut.activated.connect(self.redo_action)
        
        # Save shortcut
        save_shortcut = QShortcut(QKeySequence.Save, self)
        save_shortcut.activated.connect(self.save_collage)
        
        # Delete selection shortcut
        delete_shortcut = QShortcut(QKeySequence.Delete, self)
        delete_shortcut.activated.connect(self.delete_selected)
        
        # Select all shortcut
        select_all_shortcut = QShortcut(QKeySequence.SelectAll, self)
        select_all_shortcut.activated.connect(self.select_all_cells)
        
        # Deselect shortcut
        deselect_shortcut = QShortcut(QKeySequence("Escape"), self)
        deselect_shortcut.activated.connect(self.deselect_all_cells)
        
        # Merge/Split shortcuts
        merge_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        merge_shortcut.activated.connect(self.merge_selected_cells)
        
        split_shortcut = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        split_shortcut.activated.connect(self.split_selected_cell)

    def undo_action(self):
        """Handle undo action."""
        self.undo_stack.undo()
        self.update()
        logging.info("Undo action performed")

    def redo_action(self):
        """Handle redo action."""
        self.undo_stack.redo()
        self.update()
        logging.info("Redo action performed")

    def delete_selected(self):
        """Clear images from selected cells."""
        for cell in self.collage.cells:
            if cell.selected:
                cell.clearImage()
        logging.info("Deleted images from selected cells")

    def select_all_cells(self):
        """Select all cells in the collage."""
        for cell in self.collage.cells:
            cell.selected = True
            cell.update()
        logging.info("Selected all cells")

    def deselect_all_cells(self):
        """Deselect all cells in the collage."""
        for cell in self.collage.cells:
            cell.selected = False
            cell.update()
        logging.info("Deselected all cells")

    def create_controls_panel(self):
        controls_layout = QHBoxLayout()

        # Create a group for grid controls
        grid_group = QHBoxLayout()
        grid_group.addWidget(QLabel("Grid:"))
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setValue(2)
        self.rows_spin.setPrefix("Rows: ")
        self.rows_spin.setToolTip("Set number of rows in the grid")
        
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1)
        self.cols_spin.setValue(2)
        self.cols_spin.setPrefix("Cols: ")
        self.cols_spin.setToolTip("Set number of columns in the grid")
        
        update_button = QPushButton("Update Grid")
        update_button.setToolTip("Apply grid size changes")
        update_button.clicked.connect(self.update_collage)
        
        grid_group.addWidget(self.rows_spin)
        grid_group.addWidget(self.cols_spin)
        grid_group.addWidget(update_button)

        # Create a group for merge/split controls with better styling
        merge_group = QHBoxLayout()
        merge_group.addWidget(QLabel("Cell Operations:"))
        
        merge_button = QPushButton("Merge Cells")
        merge_button.setToolTip("Merge selected cells (Ctrl+M)\nSelect multiple cells with Ctrl+Click")
        merge_button.clicked.connect(self.merge_selected_cells)
        merge_button.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                background-color: #4CAF50;
                color: white;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        split_button = QPushButton("Split Cell")
        split_button.setToolTip("Split merged cell back to individual cells (Ctrl+Shift+M)")
        split_button.clicked.connect(self.split_selected_cell)
        split_button.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                background-color: #2196F3;
                color: white;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
        """)
        
        merge_group.addWidget(merge_button)
        merge_group.addWidget(split_button)

        # Create save/export controls
        save_group = QHBoxLayout()
        save_button = QPushButton("Save Collage")
        save_button.setToolTip("Save the collage as an image (Ctrl+S)")
        save_button.clicked.connect(self.save_collage)
        
        batch_import_button = QPushButton("Batch Import")
        batch_import_button.setToolTip("Import multiple images at once")
        batch_import_button.clicked.connect(self.handle_batch_import)
        
        save_group.addWidget(save_button)
        save_group.addWidget(batch_import_button)

        # Layout vertical para organizar los controles
        controls_vertical = QVBoxLayout()
        
        # First row with main controls
        row1 = QHBoxLayout()
        row1.addLayout(grid_group)
        row1.addSpacing(20)  # Add spacing between groups
        row1.addLayout(merge_group)
        row1.addSpacing(20)
        row1.addLayout(save_group)
        row1.addStretch()  # Push everything to the left
        
        # Image quality controls with better organization
        quality_group = QHBoxLayout()
        quality_group.addWidget(QLabel("Image Quality:"))
        
        self.transform_combo = QComboBox()
        self.transform_combo.addItem("Lossless Quality", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("High Quality", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("Balanced", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("Fast", Qt.TransformationMode.FastTransformation)
        self.transform_combo.setCurrentIndex(0)  # Set Lossless as default
        self.transform_combo.currentIndexChanged.connect(self.update_image_quality)
        self.transform_combo.setToolTip("Select image transformation quality\nLossless: Preserves original quality\nHigh Quality: Very good quality\nBalanced: Good quality with better performance\nFast: Faster but lower quality")
        
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItem("Keep Aspect Ratio", Qt.KeepAspectRatio)
        self.aspect_combo.addItem("Stretch to Fill", Qt.IgnoreAspectRatio)
        self.aspect_combo.addItem("Fit Inside", Qt.KeepAspectRatioByExpanding)
        self.aspect_combo.setCurrentIndex(0)
        self.aspect_combo.currentIndexChanged.connect(self.update_image_quality)
        self.aspect_combo.setToolTip("Select how images should fit in cells")
        
        quality_group.addWidget(self.transform_combo)
        quality_group.addWidget(self.aspect_combo)
        quality_group.addStretch()

        # Caption controls with better organization
        caption_group = QHBoxLayout()
        caption_group.addWidget(QLabel("Caption Format:"))
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 36)
        self.font_size_spin.setValue(14)
        self.font_size_spin.setPrefix("Size: ")
        self.font_size_spin.valueChanged.connect(self.update_caption_format)
        self.font_size_spin.setToolTip("Set caption font size")

        self.bold_checkbox = QCheckBox("Bold")
        self.bold_checkbox.setChecked(True)
        self.bold_checkbox.toggled.connect(self.update_caption_format)
        
        self.italic_checkbox = QCheckBox("Italic")
        self.italic_checkbox.setChecked(False)
        self.italic_checkbox.toggled.connect(self.update_caption_format)
        
        self.underline_checkbox = QCheckBox("Underline")
        self.underline_checkbox.setChecked(False)
        self.underline_checkbox.toggled.connect(self.update_caption_format)
        
        caption_group.addWidget(self.font_size_spin)
        caption_group.addWidget(self.bold_checkbox)
        caption_group.addWidget(self.italic_checkbox)
        caption_group.addWidget(self.underline_checkbox)
        caption_group.addStretch()

        # Add all groups to the main vertical layout
        controls_vertical.addLayout(row1)
        controls_vertical.addSpacing(10)
        controls_vertical.addLayout(quality_group)
        controls_vertical.addSpacing(10)
        controls_vertical.addLayout(caption_group)
        
        return controls_vertical

    def merge_selected_cells(self):
        """Handle merge cells action from UI."""
        self.collage.merge_selected_cells()

    def split_selected_cell(self):
        """Handle split cell action from UI."""
        selected_cells = [cell for cell in self.collage.cells if cell.selected]
        if not selected_cells:
            QMessageBox.warning(self, "Split Cell", "Please select a merged cell to split")
            return

        # Find any merged cell in selection
        for cell in selected_cells:
            pos = self.collage.get_cell_position(cell)
            if pos:
                row, col = pos
                # Check if this is a merged cell or part of one
                merged_found = False
                for (mr, mc), (mrs, mcs) in list(self.collage.merged_cells.items()):
                    if (mr <= row < mr + mrs) and (mc <= col < mc + mcs):
                        # Found a merged cell, attempt to split it
                        if self.collage.split_merged_cell(mr, mc):
                            merged_found = True
                            break
                if merged_found:
                    break
        else:
            QMessageBox.warning(self, "Split Cell", "Selected cell is not merged")

    def update_caption_format(self):
        # Obtener valores actuales de los controles
        font_size = self.font_size_spin.value()
        bold = self.bold_checkbox.isChecked()
        italic = self.italic_checkbox.isChecked()
        underline = self.underline_checkbox.isChecked()
        # Actualizar cada celda del collage
        for cell in self.collage.cells:
            cell.use_caption_formatting = True
            cell.caption_font_size = font_size
            cell.caption_bold = bold
            cell.caption_italic = italic
            cell.caption_underline = underline
            cell.update()
        logging.info("Formato caption actualizado: tamaño=%d, bold=%s, italic=%s, underline=%s",
                     font_size, bold, italic, underline)

    def handle_error(self, message: str, detailed_error: str = None):
        """Handle errors with proper user feedback."""
        QMessageBox.critical(
            self,
            "Error",
            message + ("\n\nDetailed error:\n" + detailed_error if detailed_error else "")
        )
        logging.error(message + (f": {detailed_error}" if detailed_error else ""))

    def update_image_quality(self):
        try:
            # Update quality settings for all cells
            transform_mode = self.transform_combo.currentData()
            aspect_mode = self.aspect_combo.currentData()
            
            # Store current cursor
            current_cursor = self.cursor()
            self.setCursor(Qt.WaitCursor)
            
            # Batch update all cells
            for cell in self.collage.cells:
                if cell.pixmap:  # Only process cells with images
                    cell.transformation_mode = transform_mode
                    cell.aspect_ratio_mode = aspect_mode
                    if cell.original_pixmap:
                        # Regenerate scaled version from original
                        cell.pixmap = cell.original_pixmap
                    cell.update()
            
            # Restore cursor
            self.setCursor(current_cursor)
            
            logging.info("Image quality updated: transform=%s, aspect=%s",
                        self.transform_combo.currentText(),
                        self.aspect_combo.currentText())
                        
        except Exception as e:
            self.handle_error("Failed to update image quality", str(e))
            
    def closeEvent(self, event):
        """Handle application closure."""
        try:
            # Clean up any temporary files or resources
            for cell in self.collage.cells:
                if hasattr(cell, 'cleanup'):
                    cell.cleanup()
                    
            # Save application state/settings if needed
            logging.info("Application closing, cleanup complete")
            event.accept()
            
        except Exception as e:
            self.handle_error("Error during cleanup", str(e))

    def update_collage(self):
        rows = self.rows_spin.value()
        columns = self.cols_spin.value()
        logging.info("Actualizando collage: %d filas x %d columnas.", rows, columns)
        self.collage.update_grid(rows, columns)

    def save_collage(self):
        self.save_manager.save_collage(self.collage, self)

    def show_save_dialog(self):
        """Show advanced save dialog with preview and options."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Save Collage")
        dialog.setMinimumWidth(600)
        
        layout = QVBoxLayout(dialog)
        
        # Preview
        preview_label = QLabel()
        preview_pixmap = self.collage.grab().scaled(
            300, 300, 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        preview_label.setPixmap(preview_pixmap)
        layout.addWidget(preview_label, alignment=Qt.AlignCenter)
        
        # Format selection
        format_layout = QHBoxLayout()
        format_label = QLabel("Format:")
        format_combo = QComboBox()
        format_combo.addItems(["PNG", "JPEG", "WebP"])
        format_layout.addWidget(format_label)
        format_layout.addWidget(format_combo)
        layout.addLayout(format_layout)
        
        # Quality settings
        quality_layout = QHBoxLayout()
        quality_label = QLabel("Quality:")
        quality_slider = QSlider(Qt.Horizontal)
        quality_slider.setRange(1, 100)
        quality_slider.setValue(95)
        quality_value = QLabel("95%")
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(quality_slider)
        quality_layout.addWidget(quality_value)
        layout.addLayout(quality_layout)
        
        # Resolution multiplier
        resolution_layout = QHBoxLayout()
        resolution_label = QLabel("Resolution:")
        resolution_combo = QComboBox()
        resolution_combo.addItems(["1x", "2x", "4x"])
        resolution_layout.addWidget(resolution_label)
        resolution_layout.addWidget(resolution_combo)
        layout.addLayout(resolution_layout)
        
        # Connect quality slider to label
        quality_slider.valueChanged.connect(
            lambda v: quality_value.setText(f"{v}%")
        )
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.Accepted:
            return {
                'format': format_combo.currentText().lower(),
                'quality': quality_slider.value(),
                'resolution': int(resolution_combo.currentText()[0])
            }
        return None

    def optimize_for_format(self, pixmap: QPixmap, format: str, quality: int) -> QPixmap:
        """Optimize pixmap for specific output format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB with white background for JPEG
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve DPI
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image
                
        elif format == 'webp':
            # Convert to ARGB32_Premultiplied for WebP
            if image.format() != QImage.Format_ARGB32_Premultiplied:
                return image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
        
        return image

# ========================================================
# Widget de cada celda del collage (cuadrada)
# ========================================================

class CollageCell(QWidget):
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap = None                # Display version of the image
        self.original_pixmap = None       # Original high-quality version
        self.original_image = None        # Store original QImage for maximum quality
        self.caption = ""                 # Text optional for the image
        self.use_caption_formatting = True  # Master flag for applying format
        self.caption_font_size = 14
        self.caption_bold = True
        self.caption_italic = False
        self.caption_underline = False
        self.transformation_mode = Qt.SmoothTransformation  # Default high quality transformation
        self.aspect_ratio_mode = Qt.KeepAspectRatio        # Default aspect ratio mode
        self.row_span = 1  # Number of rows this cell spans
        self.col_span = 1  # Number of columns this cell spans
        self.setAcceptDrops(True)
        self.setFixedSize(cell_size, cell_size)
        self.setStyleSheet("background-color: transparent;")
        self.selected = False  # Add selected state
        logging.info("Celda %d creada (tamaño %dx%d).", self.cell_id, cell_size, cell_size)

    def setSpan(self, row_span: int, col_span: int):
        """Set the cell's row and column span."""
        self.row_span = max(1, row_span)
        self.col_span = max(1, col_span)
        new_width = self.width() * self.col_span
        new_height = self.height() * self.row_span
        self.setFixedSize(new_width, new_height)
        self.update()
        logging.info(f"Cell {self.cell_id} span updated to {row_span}x{col_span}")

    def setImage(self, pixmap: QPixmap):
        """Set the image for this cell, preserving original quality."""
        # Store the original high quality version
        self.original_pixmap = pixmap
        # Create a display version
        self.pixmap = pixmap.copy()  # Make a copy for display
        self.update()
        logging.info("Cell %d: image loaded and original quality preserved.", self.cell_id)

    def clearImage(self):
        self.pixmap = None
        self.original_pixmap = None
        self.caption = ""
        self.update()

    def paintEvent(self, event):
        """Paint cell content with maximum quality preservation."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        rect = self.rect()
        
        # Draw selection border if selected
        if self.selected:
            pen = painter.pen()
            pen.setColor(QColor(52, 152, 219))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
            
            if any(c.selected for c in self.parent().cells if c != self):
                corner_size = 15
                pen.setColor(QColor(46, 204, 113))
                painter.setPen(pen)
                painter.drawLine(rect.left(), rect.top(), rect.left() + corner_size, rect.top())
                painter.drawLine(rect.left(), rect.top(), rect.left(), rect.top() + corner_size)
                painter.drawLine(rect.right(), rect.bottom(), rect.right() - corner_size, rect.bottom())
                painter.drawLine(rect.right(), rect.bottom(), rect.right(), rect.bottom() - corner_size)
        
        # Draw cell content
        if self.pixmap:
            # Use original high-quality pixmap if available
            source_pixmap = self.original_pixmap if hasattr(self, 'original_pixmap') and self.original_pixmap else self.pixmap
            
            # Scale with maximum quality preservation
            scaled = source_pixmap.scaled(
                rect.size(), 
                self.aspect_ratio_mode,
                Qt.SmoothTransformation  # Always use high quality transformation
            )
            
            # Center the image
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            target = QRect(x, y, scaled.width(), scaled.height())
            
            # Draw with quality preservation
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.drawPixmap(target, scaled, scaled.rect())
            
            # Draw caption if present
            if self.caption:
                self._render_high_quality_caption(painter, target)
                
        else:
            # Draw placeholder with better styling
            painter.fillRect(rect, QColor(245, 245, 245))
            painter.setPen(QColor(180, 180, 180))
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "Drop Image Here\nClick to Select")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() == Qt.ControlModifier:
                # Toggle selection with Ctrl+Click
                self.selected = not self.selected
                self.update()
                logging.info("Celda %d: selección cambiada a %s.", self.cell_id, self.selected)
            elif self.pixmap:
                # Original drag behavior only if there's an image
                logging.info("Celda %d: iniciando drag.", self.cell_id)
                drag = QDrag(self)
                mime_data = ImageMimeData(self.pixmap, self)
                drag.setMimeData(mime_data)
                preview = self.pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(preview)
                result = drag.exec(Qt.MoveAction)
                logging.info("Celda %d: drag finalizado (resultado: %s).", self.cell_id, result)

    def mouseDoubleClickEvent(self, event):
        # Permite editar el caption de la imagen
        if self.pixmap:
            new_caption, ok = QInputDialog.getText(self, "Editar Título", "Título de la imagen:", text=self.caption)
            if ok:
                self.caption = new_caption
                self.update()
                logging.info("Celda %d: caption actualizado a '%s'.", self.cell_id, self.caption)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        logging.info("Celda %d: dropEvent.", self.cell_id)
        mime = event.mimeData()
        # Caso 1: Intercambio interno
        if mime.hasFormat("application/x-pixmap"):
            source_cell = getattr(mime, "source_widget", None)
            if source_cell and source_cell is not self:
                logging.info("Celda %d: intercambiando imagen con Celda %d.", self.cell_id, source_cell.cell_id)
                self.pixmap, source_cell.pixmap = source_cell.pixmap, self.pixmap
                self.original_pixmap, source_cell.original_pixmap = source_cell.original_pixmap, self.original_pixmap
                self.caption, source_cell.caption = source_cell.caption, self.caption
                self.update()
                source_cell.update()
                event.acceptProposedAction()
                return
        # Caso 2: Cargar imagen externa
        elif mime.hasUrls():
            file_path = mime.urls()[0].toLocalFile()
            if file_path:
                self.loadExternalImage(file_path, event)
                return
        event.ignore()

    def loadExternalImage(self, file_path, event):
        """Load external image with maximum quality preservation."""
        try:
            logging.info("Cell %d: loading high-quality image from %s", self.cell_id, file_path)
            
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)  # Apply EXIF orientation
            reader.setQuality(100)  # Maximum quality
            reader.setAllocationLimit(0)  # No memory limits for better quality
            
            # Get original image info
            original_size = reader.size()
            if not original_size.isValid():
                raise ValueError(f"Invalid image size: {reader.errorString()}")
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise ValueError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32,
                    Qt.NoOpaqueDetection  # Preserve alpha channel quality
                )
                # Restore original DPI
                original_image.setDotsPerMeterX(dpmX)
                original_image.setDotsPerMeterY(dpmY)
            
            # Create high-quality pixmap preserving all attributes
            self.original_pixmap = QPixmap.fromImage(original_image)
            self.original_image = original_image  # Keep original for quality preservation
            
            # Create optimized display version
            display_size = self.size()
            if original_size.width() > display_size.width() * 3 or original_size.height() > display_size.height() * 3:
                # Scale down for display while maintaining quality
                self.pixmap = self.original_pixmap.scaled(
                    display_size * 2,  # Keep 2x resolution for quality
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            else:
                # Use original size if not too large
                self.pixmap = self.original_pixmap.copy()
            
            # Cache the original high-quality version
            metadata = {
                'size': original_size,
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'timestamp': QFileInfo(file_path).lastModified()
            }
            image_cache.put(file_path, self.original_pixmap, metadata)
            
            self.update()
            event.acceptProposedAction()
            logging.info(f"Successfully loaded high-quality image in cell {self.cell_id}")
            
        except Exception as e:
            logging.error("Cell %d: Error loading image: %s", self.cell_id, str(e))
            event.ignore()

    def cleanup(self):
        """Clean up resources when cell is destroyed."""
        # Clear image data
        self.pixmap = None
        self.original_pixmap = None
        self.scaled_pixmap = None
        
        # Force garbage collection of large objects
        import gc
        gc.collect()

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()
        # Remove incorrect super().__del__() call since QWidget doesn't have a __del__ method

    def optimize_memory(self):
        """Optimize memory usage by clearing cached scaled images."""
        if hasattr(self, 'scaled_pixmap') and self.scaled_pixmap:
            self.scaled_pixmap = None
            gc.collect()  # Force garbage collection
        
        # Only keep high-quality original if needed
        if self.pixmap and self.original_pixmap:
            # Check if original is significantly larger than displayed size
            orig_size = self.original_pixmap.size()
            display_size = self.size()
            
            if (orig_size.width() > display_size.width() * 2 or 
                orig_size.height() > display_size.height() * 2):
                # Create an optimized version and release the original
                optimized = self.original_pixmap.scaled(
                    display_size * 2,  # Keep 2x resolution for zooming
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.original_pixmap = optimized
                gc.collect()
                
    def batch_process_images(self, image_paths: list):
        """Process multiple images efficiently."""
        for path in image_paths:
            try:
                # Check cache first
                cached_pixmap, metadata = image_cache.get(path)
                if cached_pixmap:
                    self.setImage(cached_pixmap)
                    continue
                
                # Load and process new image
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                
                # Get image info before loading
                size = reader.size()
                if size.width() > 4000 or size.height() > 4000:
                    # Scale down large images
                    scale = 4000 / max(size.width(), size.height())
                    reader.setScaledSize((size * scale).toSize())
                
                image = reader.read()
                if image.isNull():
                    raise ValueError(f"Failed to load image: {reader.errorString()}")
                
                # Convert to optimal format
                if image.format() != QImage.Format_ARGB32:
                    image = image.convertToFormat(QImage.Format_ARGB32)
                
                # Create pixmap and cache it
                pixmap = QPixmap.fromImage(image)
                metadata = {
                    'size': size,
                    'format': reader.format().data().decode(),
                    'timestamp': QFileInfo(path).lastModified()
                }
                image_cache.put(path, pixmap, metadata)
                
                self.setImage(pixmap)
                
            except Exception as e:
                logging.error(f"Error processing image {path}: {str(e)}")
                continue

    def _onImageLoaded(self, pixmap: QPixmap, filename: str):
        """Handle loaded image with quality preservation."""
        try:
        try:
            # Store original uncompressed image
            self.original_pixmap = pixmap.copy()  # Make a deep copy of original
            
            # Create display version at cell size while maintaining quality
            display_pixmap = pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Set the display version
            self.setImage(display_pixmap)
            
            # Cache the original high-quality version
            metadata = ImageOptimizer.process_metadata(filename)
            image_cache.put(filename, self.original_pixmap, metadata)
            
            # Close progress dialog if exists
            if hasattr(self, 'progress'):
                self.progress.close()
                delattr(self, 'progress')
                
            # Clean up the loader thread
            if hasattr(self, 'loader'):
                self.loader.deleteLater()
                delattr(self, 'loader')
            
            logging.info(f"Cell {self.cell_id}: Image loaded at original quality")
            
        except Exception as e:
            logging.error(f"Cell {self.cell_id}: Error in image loading: {str(e)}")
            if hasattr(self, 'progress'):
                self.progress.close()
                delattr(self, 'progress')

    def render_high_quality(self, painter: QPainter):
        """Render cell at maximum quality for saving."""
        if not self.pixmap:
            return
            
        rect = self.rect()
        pos = self.mapTo(self.parent(), QPoint(0, 0))
        target_rect = QRect(pos, rect.size())
        
        # Use original high-quality pixmap if available, fall back to regular pixmap if not
        source_pixmap = getattr(self, 'original_pixmap', None) or self.pixmap
        
        # Configure device pixel ratio for high DPI support
        if hasattr(source_pixmap, 'devicePixelRatio'):
            source_pixmap.setDevicePixelRatio(1.0)  # Ensure 1:1 pixel mapping
        
        painter.save()
        # Enable all quality-related render hints
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        # Scale image while preserving aspect ratio and maximum quality
        scaled_pixmap = source_pixmap.scaled(
            target_rect.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Center the image in the cell
        x = target_rect.x() + (target_rect.width() - scaled_pixmap.width()) // 2
        y = target_rect.y() + (target_rect.height() - scaled_pixmap.height()) // 2
        
        # Draw using composition mode that preserves quality
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(x, y, scaled_pixmap)
        
        # Draw caption with optimal quality if present
        if self.caption:
            self._render_high_quality_caption(painter, QRect(x, y, scaled_pixmap.width(), scaled_pixmap.height()))
        
        painter.restore()
        
    def _render_high_quality_caption(self, painter: QPainter, image_rect: QRect):
        """Render caption with maximum quality."""
        font = painter.font()
        if self.use_caption_formatting:
            font.setPointSize(self.caption_font_size)
            font.setBold(self.caption_bold)
            font.setItalic(self.caption_italic)
            font.setUnderline(self.caption_underline)
            # Enable kerning and other font optimizations
            font.setKerning(True)
            font.setHintingPreference(QFont.PreferFullHinting)
        painter.setFont(font)
        
        # Calculate optimal text positioning
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(self.caption)
        text_rect.moveCenter(QPoint(
            image_rect.center().x(),
            image_rect.bottom() - text_rect.height()//2 - 5
        ))
        
        # Draw high-quality text background
        background_rect = text_rect.adjusted(-6, -3, 6, 3)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.fillRect(background_rect, QColor(0, 0, 0, 160))
        
        # Draw text with high-quality anti-aliasing
        painter.setPen(QColor(0, 0, 0, 160))  # Shadow
        painter.drawText(text_rect.adjusted(1, 1, 1, 1), Qt.AlignCenter, self.caption)
        painter.setPen(Qt.white)  # Main text
        painter.drawText(text_rect, Qt.AlignCenter, self.caption)

    def getHighQualityRendering(self) -> QPixmap:
        """Get a high quality rendered version of the cell content."""
        if not self.pixmap:
            return None
            
        # Always use original high-quality pixmap if available
        source_pixmap = self.original_pixmap if hasattr(self, 'original_pixmap') and self.original_pixmap else self.pixmap
        
        # Create target pixmap at desired size
        target_size = self.size()
        output = QPixmap(target_size)
        output.fill(Qt.transparent)
        
        # Set up painter with maximum quality settings
        painter = QPainter(output)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        # Calculate scaling while preserving aspect ratio
        source_rect = source_pixmap.rect()
        target_rect = self.rect()
        
        # Scale and center the image
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(target_rect.size(), Qt.KeepAspectRatio)
            x = target_rect.x() + (target_rect.width() - scaled_size.width()) // 2
            y = target_rect.y() + (target_rect.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw with maximum quality
        painter.drawPixmap(target_rect, source_pixmap, source_rect)
        
        # Draw caption if present
        if self.caption:
            self._render_high_quality_caption(painter, target_rect)
        
        painter.end()
        return output
        
    def _create_high_quality_pixmap(self, size: QSize) -> QPixmap:
        """Create a high quality scaled version of the image."""
        if not self.original_pixmap:
            return None
            
        # Create intermediate high-resolution pixmap
        intermediate_size = size * 2  # Work at 2x target size for better quality
        intermediate = QPixmap(intermediate_size)
        intermediate.fill(Qt.transparent)
        
        # High quality painting
        painter = QPainter(intermediate)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Scale while preserving aspect ratio
        source_rect = self.original_pixmap.rect()
        target_rect = QRect(QPoint(0, 0), intermediate_size)
        
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(intermediate_size, Qt.KeepAspectRatio)
            x = (intermediate_size.width() - scaled_size.width()) // 2
            y = (intermediate_size.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw at high resolution
        painter.drawPixmap(target_rect, self.original_pixmap, source_rect)
        painter.end()
        
        # Scale down to target size with high quality
        return intermediate.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _preserve_image_attributes(self, image: QImage, source_image: QImage = None) -> QImage:
        """Preserve image attributes during transformations."""
        if source_image and hasattr(source_image, 'dotsPerMeterX'):
            # Preserve DPI information
            image.setDotsPerMeterX(source_image.dotsPerMeterX())
            image.setDotsPerMeterY(source_image.dotsPerMeterY())
        
        # Ensure optimal color space
        if image.format() != QImage.Format_ARGB32_Premultiplied:
            image = image.convertToFormat(
                QImage.Format_ARGB32_Premultiplied,
                Qt.NoOpaqueDetection  # Preserve alpha channel quality
            )
        
        return image
        
    def scale_with_quality(self, pixmap: QPixmap, target_size: QSize, keep_attributes: bool = True) -> QPixmap:
        """Scale image while preserving maximum quality."""
        if not pixmap:
            return None
            
        # Work at 2x target size for better quality during scaling
        intermediate_size = target_size * 2
        
        # Create intermediate high-resolution pixmap
        intermediate = QPixmap(intermediate_size)
        intermediate.fill(Qt.transparent)
        
        # High quality painting to intermediate
        painter = QPainter(intermediate)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Draw at high resolution
        source_rect = pixmap.rect()
        target_rect = QRect(QPoint(0, 0), intermediate_size)
        
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(intermediate_size, Qt.KeepAspectRatio)
            x = (intermediate_size.width() - scaled_size.width()) // 2
            y = (intermediate_size.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw original image to intermediate
        painter.drawPixmap(target_rect, pixmap, source_rect)
        painter.end()
        
        # Convert to image for attribute preservation
        if keep_attributes:
            intermediate_image = intermediate.toImage()
            source_image = pixmap.toImage()
            intermediate_image = self._preserve_image_attributes(intermediate_image, source_image)
            intermediate = QPixmap.fromImage(intermediate_image)
        
        # Scale down to final size with high quality
        result = intermediate.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Final attribute preservation if needed
        if keep_attributes:
            result_image = result.toImage()
            result_image = self._preserve_image_attributes(result_image, source_image)
            result = QPixmap.fromImage(result_image)
        
        return result

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

# ========================================================
# Worker, TaskQueue, and related classes
# ========================================================

class WorkerSignals(QObject):
    """Defines signals for worker threads."""
    started = Signal()
    finished = Signal()
    error = Signal(str)
    progress = Signal(int)
    result = Signal(object)

class Worker(QRunnable):
    """Base worker class for background tasks."""
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
    def run(self):
        """Execute the task."""
        try:
            self.signals.started.emit()
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

class TaskQueue:
    """Manages queued tasks with priority handling."""
    def __init__(self, max_concurrent=4):
        self.queue = []
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(max_concurrent)
        self.mutex = QMutex()
        self.processing = False

    def add_task(self, task, priority=0):
        """Add a task to the queue with optional priority."""
        with QMutexLocker(self.mutex):
            self.queue.append((priority, task))
            self.queue.sort(key=lambda x: x[0], reverse=True)
            
        if not self.processing:
            self.process_next()

    def process_next(self):
        """Process the next task in the queue."""
        with QMutexLocker(self.mutex):
            if not self.queue:
                self.processing = False
                return
                
            self.processing = True
            _, task = self.queue.pop(0)
            
        self.thread_pool.start(task)
        task.signals.finished.connect(self.process_next)

    def clear(self):
        """Clear all pending tasks."""
        with QMutexLocker(self.mutex):
            self.queue.clear()

    def is_empty(self):
        """Check if queue is empty."""
        with QMutexLocker(self.mutex):
            return len(self.queue) == 0

class ImageLoadWorker(QThread):
    """Worker thread for loading and processing images with maximum quality preservation."""
    finished = Signal(QPixmap, str)  # Emits processed pixmap and filename
    error = Signal(str)  # Emits error message if loading fails
    progress = Signal(int)  # Emits progress percentage
    
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._cancelled = False
        
    def run(self):
        try:
            # Configure image reader for maximum quality
            reader = QImageReader(self.file_path)
            reader.setAutoTransform(True)  # Apply EXIF orientation
            reader.setQuality(100)  # Maximum quality
            reader.setAllocationLimit(0)  # No memory limits for better quality
            
            # Get original image info
            original_size = reader.size()
            if not original_size.isValid():
                self.error.emit(f"Invalid image size: {reader.errorString()}")
                return
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                self.error.emit(f"Failed to load image: {reader.errorString()}")
                return
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32,
                    Qt.NoOpaqueDetection  # Preserve alpha channel quality
                )
                # Restore original DPI
                original_image.setDotsPerMeterX(dpmX)
                original_image.setDotsPerMeterY(dpmY)
            
            # Create high-quality pixmap preserving all attributes
            self.original_pixmap = QPixmap.fromImage(original_image)
            self.original_image = original_image  # Keep original for quality preservation
            
            # Create optimized display version
            display_size = self.size()
            if original_size.width() > display_size.width() * 3 or original_size.height() > display_size.height() * 3:
                # Scale down for display while maintaining quality
                self.pixmap = self.original_pixmap.scaled(
                    display_size * 2,  # Keep 2x resolution for quality
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            else:
                # Use original size if not too large
                self.pixmap = self.original_pixmap.copy()
            
            # Cache the original high-quality version
            metadata = {
                'size': original_size,
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'timestamp': QFileInfo(self.file_path).lastModified()
            }
            image_cache.put(self.file_path, self.original_pixmap, metadata)
            
            self.update()
            self.finished.emit(self.pixmap, self.file_path)
            logging.info(f"Successfully loaded high-quality image in cell {self.cell_id}")
            
        except Exception as e:
            self.error.emit(str(e))
            
    def cancel(self):
        self._cancelled = True

class BatchProcessor:
    """Handles batch processing of multiple images."""
    def __init__(self, parent):
        self.parent = parent
        self.processing_queue = []
        self.current_worker = None
        
    def process_files(self, file_paths: list, target_size: QSize = None):
        """Start batch processing of files."""
        self.processing_queue = file_paths
        
        # Create and configure progress dialog
        progress = QProgressDialog("Processing images...", "Cancel", 0, len(file_paths), self.parent)
        progress.setWindowModality(Qt.WindowModal)
        
        # Create worker thread
        self.current_worker = ImageLoadWorker(file_paths, target_size)
        
        # Connect signals
        self.current_worker.finished.connect(self._on_image_processed)
        self.current_worker.error.connect(self._on_error)
        self.current_worker.progress.connect(progress.setValue)
        progress.canceled.connect(self.current_worker.cancel)
        
        # Start processing
        self.current_worker.start()
        progress.exec_()
        
    def _on_image_processed(self, pixmap: QPixmap, file_path: str):
        """Handle processed image."""
        # Add to cache
        metadata = ImageOptimizer.process_metadata(file_path)
        image_cache.put(file_path, pixmap, metadata)
        
    def _on_error(self, error_message: str):
        """Handle processing error."""
        QMessageBox.warning(
            self.parent,
            "Processing Error",
            error_message
        )

class AutosaveManager:
    """Manages automatic saving of collage state."""
    def __init__(self, parent):
        self.parent = parent
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self.perform_autosave)
        self.autosave_interval = 5 * 60 * 1000  # 5 minutes in milliseconds
        self.autosave_path = "autosave"
        self.ensure_autosave_dir()
        
    def ensure_autosave_dir(self):
        """Ensure autosave directory exists."""
        if not os.path.exists(self.autosave_path):
            os.makedirs(self.autosave_path)
            
    def start(self):
        """Start autosave timer."""
        self.autosave_timer.start(self.autosave_interval)
        
    def stop(self):
        """Stop autosave timer."""
        self.autosave_timer.stop()
        
    def perform_autosave(self):
        """Perform the autosave operation."""
        try:
            # Generate autosave filename with timestamp
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
            filename = f"collage_autosave_{timestamp}.json"
            filepath = os.path.join(self.autosave_path, filename)
            
            # Get collage state
            state = self.parent.get_collage_state()
            
            # Save state to file
            with open(filepath, 'w') as f:
                json.dump(state, f)
                
            # Clean up old autosaves (keep last 5)
            self.cleanup_old_autosaves()
            
            logging.info(f"Autosave completed: {filepath}")
            
        except Exception as e:
            logging.error(f"Autosave failed: {str(e)}")
            
    def cleanup_old_autosaves(self):
        """Keep only the 5 most recent autosaves."""
        try:
            files = glob.glob(os.path.join(self.autosave_path, "collage_autosave_*.json"))
            files.sort(reverse=True)
            
            # Remove old files
            for old_file in files[5:]:
                try:
                    os.remove(old_file)
                except:
                    pass
                    
        except Exception as e:
            logging.error(f"Autosave cleanup failed: {str(e)}")
            
    def get_latest_autosave(self):
        """Get the most recent autosave file."""
        try:
            files = glob.glob(os.path.join(self.autosave_path, "collage_autosave_*.json"))
            if files:
                return max(files, key=os.path.getctime)
        except Exception as e:
            logging.error(f"Failed to get latest autosave: {str(e)}")
        return None

class PerformanceMonitor:
    """Monitors and optimizes application performance."""
    def __init__(self):
        self.memory_threshold = 500 * 1024 * 1024  # 500MB
        self.last_cleanup = QDateTime.currentDateTime()
        self.cleanup_interval = 300  # 5 minutes in seconds
        
    def check_memory_usage(self):
        """Check current memory usage and optimize if needed."""
        try:
            if HAS_PSUTIL:
                process = psutil.Process()
                memory_info = process.memory_info()
                
                if memory_info.rss > self.memory_threshold:
                    current_time = QDateTime.currentDateTime()
                    if self.last_cleanup.secsTo(current_time) >= self.cleanup_interval:
                        self.optimize_memory_usage()
                        self.last_cleanup = current_time
                    
        except Exception as e:
            logging.warning(f"Memory monitoring error: {str(e)}")
            
    def optimize_memory_usage(self):
        """Perform memory optimization."""
        # Clear image cache if too large
        if len(image_cache.cache) > image_cache.max_size * 0.8:
            image_cache._cleanup()
            
        # Force Python garbage collection
        gc.collect()
        
        logging.info("Memory optimization performed")

class ErrorHandlingManager:
    """Manages error handling and recovery for image operations."""
    
    class ImageOperationError(Exception):
        """Base exception for image operations."""
        pass
        
    class LoadError(ImageOperationError):
        """Error loading an image."""
        pass
        
    class SaveError(ImageOperationError):
        """Error saving an image."""
        pass
        
    class FormatError(ImageOperationError):
        """Error with image format."""
        pass
        
    class MemoryError(ImageOperationError):
        """Error with memory allocation."""
        pass
    
    def __init__(self):
        self.error_handlers = {
            'load': self._handle_load_error,
            'save': self._handle_save_error,
            'format': self._handle_format_error,
            'memory': self._handle_memory_error
        }
        
    def handle_error(self, operation: str, error: Exception, context: dict = None) -> bool:
        """Handle an error during image operations."""
        try:
            if operation in self.error_handlers:
                return self.error_handlers[operation](error, context or {})
            return self._handle_unknown_error(error, context or {})
        except Exception as e:
            logging.error(f"Error in error handler: {str(e)}")
            return False
            
    def _handle_load_error(self, error: Exception, context: dict) -> bool:
        """Handle image loading errors."""
        file_path = context.get('file_path', 'unknown')
        error_msg = str(error)
        
        if 'Permission denied' in error_msg:
            logging.error(f"Permission denied accessing {file_path}")
            return False
            
        if 'No such file' in error_msg:
            logging.error(f"File not found: {file_path}")
            return False
            
        if 'Invalid format' in error_msg:
            logging.error(f"Invalid image format: {file_path}")
            return False
            
        logging.error(f"Unknown error loading image {file_path}: {error_msg}")
        return False
        
    def _handle_save_error(self, error: Exception, context: dict) -> bool:
        """Handle image saving errors."""
        file_path = context.get('file_path', 'unknown')
        format = context.get('format', 'unknown')
        
        if isinstance(error, IOError):
            if 'Permission denied' in str(error):
                logging.error(f"Permission denied saving to {file_path}")
                return False
                
            if 'No space' in str(error):
                logging.error(f"No disk space available saving to {file_path}")
                return False
                
        if isinstance(error, ValueError):
            if 'format' in str(error).lower():
                logging.error(f"Unsupported format {format} for {file_path}")
                return False
                
        logging.error(f"Unknown error saving image {file_path}: {str(error)}")
        return False
        
    def _handle_format_error(self, error: Exception, context: dict) -> bool:
        """Handle format conversion errors."""
        source_format = context.get('source_format', 'unknown')
        target_format = context.get('target_format', 'unknown')
        
        if 'Unsupported conversion' in str(error):
            logging.error(f"Unsupported conversion from {source_format} to {target_format}")
            return False
            
        if 'Invalid format' in str(error):
            logging.error(f"Invalid format specified: {target_format}")
            return False
            
        logging.error```python
        logging.error(f"Unknown format error converting {source_format} to {target_format}: {str(error)}")
        return False
        
    def _handle_memory_error(self, error: Exception, context: dict) -> bool:
        """Handle memory-related errors."""
        operation = context.get('operation', 'unknown')
        size = context.get('size', 'unknown')
        
        if isinstance(error, MemoryError):
            logging.error(f"Memory allocation failed for {operation} (size: {size})")
            return False
            
        logging.error(f"Unknown memory error during {operation}: {str(error)}")
        return False
        
    def _handle_unknown_error(self, error: Exception, context: dict) -> bool:
        """Handle unknown errors."""
        operation = context.get('operation', 'unknown')
        logging.error(f"Unknown error during {operation}: {str(error)}")
        return False

# ========================================================
# Ventana Principal
# ========================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker - PySide6")
        self.resize(850, 650)
        
        # Initialize undo stack
        self.undo_stack = UndoStack()
        
        # Create keyboard shortcuts
        self.create_shortcuts()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.addLayout(self.create_controls_panel())
        self.collage = CollageWidget(rows=self.rows_spin.value(), columns=self.cols_spin.value(), cell_size=260)
        main_layout.addWidget(self.collage, alignment=Qt.AlignCenter)
        logging.info("Ventana principal inicializada.")
        
        # Initialize autosave manager
        self.autosave_manager = AutosaveManager(self)
        self.autosave_manager.start()
        
        # Check for autosave
        self.check_for_autosave()
        self.batch_processor = BatchProcessor(self)
        
        # Initialize performance monitor
        self.performance_monitor = PerformanceMonitor()
        
        # Initialize error recovery manager
        self.error_recovery_manager = ErrorRecoveryManager(self)
        
        # Initialize save manager
        self.save_manager = SaveManager()
        
    def handle_batch_import(self):
        """Handle batch import of multiple images."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
        )
        
        if file_paths:
            # Calculate target size based on cell dimensions
            target_size = QSize(
                self.collage.cell_size * 2,  # 2x cell size for high quality
                self.collage.cell_size * 2
            )
            
            # Start batch processing
            self.batch_processor.process_files(file_paths, target_size)
            
    def create_shortcuts(self):
        """Create keyboard shortcuts for common actions."""
        # Undo/Redo shortcuts
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self.undo_action)
        
        redo_shortcut = QShortcut(QKeySequence.Redo, self)
        redo_shortcut.activated.connect(self.redo_action)
        
        # Save shortcut
        save_shortcut = QShortcut(QKeySequence.Save, self)
        save_shortcut.activated.connect(self.save_collage)
        
        # Delete selection shortcut
        delete_shortcut = QShortcut(QKeySequence.Delete, self)
        delete_shortcut.activated.connect(self.delete_selected)
        
        # Select all shortcut
        select_all_shortcut = QShortcut(QKeySequence.SelectAll, self)
        select_all_shortcut.activated.connect(self.select_all_cells)
        
        # Deselect shortcut
        deselect_shortcut = QShortcut(QKeySequence("Escape"), self)
        deselect_shortcut.activated.connect(self.deselect_all_cells)
        
        # Merge/Split shortcuts
        merge_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        merge_shortcut.activated.connect(self.merge_selected_cells)
        
        split_shortcut = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        split_shortcut.activated.connect(self.split_selected_cell)

    def undo_action(self):
        """Handle undo action."""
        self.undo_stack.undo()
        self.update()
        logging.info("Undo action performed")

    def redo_action(self):
        """Handle redo action."""
        self.undo_stack.redo()
        self.update()
        logging.info("Redo action performed")

    def delete_selected(self):
        """Clear images from selected cells."""
        for cell in self.collage.cells:
            if cell.selected:
                cell.clearImage()
        logging.info("Deleted images from selected cells")

    def select_all_cells(self):
        """Select all cells in the collage."""
        for cell in self.collage.cells:
            cell.selected = True
            cell.update()
        logging.info("Selected all cells")

    def deselect_all_cells(self):
        """Deselect all cells in the collage."""
        for cell in self.collage.cells:
            cell.selected = False
            cell.update()
        logging.info("Deselected all cells")

    def create_controls_panel(self):
        controls_layout = QHBoxLayout()

        # Create a group for grid controls
        grid_group = QHBoxLayout()
        grid_group.addWidget(QLabel("Grid:"))
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setValue(2)
        self.rows_spin.setPrefix("Rows: ")
        self.rows_spin.setToolTip("Set number of rows in the grid")
        
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1)
        self.cols_spin.setValue(2)
        self.cols_spin.setPrefix("Cols: ")
        self.cols_spin.setToolTip("Set number of columns in the grid")
        
        update_button = QPushButton("Update Grid")
        update_button.setToolTip("Apply grid size changes")
        update_button.clicked.connect(self.update_collage)
        
        grid_group.addWidget(self.rows_spin)
        grid_group.addWidget(self.cols_spin)
        grid_group.addWidget(update_button)

        # Create a group for merge/split controls with better styling
        merge_group = QHBoxLayout()
        merge_group.addWidget(QLabel("Cell Operations:"))
        
        merge_button = QPushButton("Merge Cells")
        merge_button.setToolTip("Merge selected cells (Ctrl+M)\nSelect multiple cells with Ctrl+Click")
        merge_button.clicked.connect(self.merge_selected_cells)
        merge_button.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                background-color: #4CAF50;
                color: white;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        split_button = QPushButton("Split Cell")
        split_button.setToolTip("Split merged cell back to individual cells (Ctrl+Shift+M)")
        split_button.clicked.connect(self.split_selected_cell)
        split_button.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                background-color: #2196F3;
                color: white;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
        """)
        
        merge_group.addWidget(merge_button)
        merge_group.addWidget(split_button)

        # Create save/export controls
        save_group = QHBoxLayout()
        save_button = QPushButton("Save Collage")
        save_button.setToolTip("Save the collage as an image (Ctrl+S)")
        save_button.clicked.connect(self.save_collage)
        
        batch_import_button = QPushButton("Batch Import")
        batch_import_button.setToolTip("Import multiple images at once")
        batch_import_button.clicked.connect(self.handle_batch_import)
        
        save_group.addWidget(save_button)
        save_group.addWidget(batch_import_button)

        # Layout vertical para organizar los controles
        controls_vertical = QVBoxLayout()
        
        # First row with main controls
        row1 = QHBoxLayout()
        row1.addLayout(grid_group)
        row1.addSpacing(20)  # Add spacing between groups
        row1.addLayout(merge_group)
        row1.addSpacing(20)
        row1.addLayout(save_group)
        row1.addStretch()  # Push everything to the left
        
        # Image quality controls with better organization
        quality_group = QHBoxLayout()
        quality_group.addWidget(QLabel("Image Quality:"))
        
        self.transform_combo = QComboBox()
        self.transform_combo.addItem("Lossless Quality", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("High Quality", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("Balanced", Qt.TransformationMode.SmoothTransformation)
        self.transform_combo.addItem("Fast", Qt.TransformationMode.FastTransformation)
        self.transform_combo.setCurrentIndex(0)  # Set Lossless as default
        self.transform_combo.currentIndexChanged.connect(self.update_image_quality)
        self.transform_combo.setToolTip("Select image transformation quality\nLossless: Preserves original quality\nHigh Quality: Very good quality\nBalanced: Good quality with better performance\nFast: Faster but lower quality")
        
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItem("Keep Aspect Ratio", Qt.KeepAspectRatio)
        self.aspect_combo.addItem("Stretch to Fill", Qt.IgnoreAspectRatio)
        self.aspect_combo.addItem("Fit Inside", Qt.KeepAspectRatioByExpanding)
        self.aspect_combo.setCurrentIndex(0)
        self.aspect_combo.currentIndexChanged.connect(self.update_image_quality)
        self.aspect_combo.setToolTip("Select how images should fit in cells")
        
        quality_group.addWidget(self.transform_combo)
        quality_group.addWidget(self.aspect_combo)
        quality_group.addStretch()

        # Caption controls with better organization
        caption_group = QHBoxLayout()
        caption_group.addWidget(QLabel("Caption Format:"))
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 36)
        self.font_size_spin.setValue(14)
        self.font_size_spin.setPrefix("Size: ")
        self.font_size_spin.valueChanged.connect(self.update_caption_format)
        self.font_size_spin.setToolTip("Set caption font size")

        self.bold_checkbox = QCheckBox("Bold")
        self.bold_checkbox.setChecked(True)
        self.bold_checkbox.toggled.connect(self.update_caption_format)
        
        self.italic_checkbox = QCheckBox("Italic")
        self.italic_checkbox.setChecked(False)
        self.italic_checkbox.toggled.connect(self.update_caption_format)
        
        self.underline_checkbox = QCheckBox("Underline")
        self.underline_checkbox.setChecked(False)
        self.underline_checkbox.toggled.connect(self.update_caption_format)
        
        caption_group.addWidget(self.font_size_spin)
        caption_group.addWidget(self.bold_checkbox)
        caption_group.addWidget(self.italic_checkbox)
        caption_group.addWidget(self.underline_checkbox)
        caption_group.addStretch()

        # Add all groups to the main vertical layout
        controls_vertical.addLayout(row1)
        controls_vertical.addSpacing(10)
        controls_vertical.addLayout(quality_group)
        controls_vertical.addSpacing(10)
        controls_vertical.addLayout(caption_group)
        
        return controls_vertical

    def merge_selected_cells(self):
        """Handle merge cells action from UI."""
        self.collage.merge_selected_cells()

    def split_selected_cell(self):
        """Handle split cell action from UI."""
        selected_cells = [cell for cell in self.collage.cells if cell.selected]
        if not selected_cells:
            QMessageBox.warning(self, "Split Cell", "Please select a merged cell to split")
            return

        # Find any merged cell in selection
        for cell in selected_cells:
            pos = self.collage.get_cell_position(cell)
            if pos:
                row, col = pos
                # Check if this is a merged cell or part of one
                merged_found = False
                for (mr, mc), (mrs, mcs) in list(self.collage.merged_cells.items()):
                    if (mr <= row < mr + mrs) and (mc <= col < mc + mcs):
                        # Found a merged cell, attempt to split it
                        if self.collage.split_merged_cell(mr, mc):
                            merged_found = True
                            break
                if merged_found:
                    break
        else:
            QMessageBox.warning(self, "Split Cell", "Selected cell is not merged")

    def update_caption_format(self):
        # Obtener valores actuales de los controles
        font_size = self.font_size_spin.value()
        bold = self.bold_checkbox.isChecked()
        italic = self.italic_checkbox.isChecked()
        underline = self.underline_checkbox.isChecked()
        # Actualizar cada celda del collage
        for cell in self.collage.cells:
            cell.use_caption_formatting = True
            cell.caption_font_size = font_size
            cell.caption_bold = bold
            cell.caption_italic = italic
            cell.caption_underline = underline
            cell.update()
        logging.info("Formato caption actualizado: tamaño=%d, bold=%s, italic=%s, underline=%s",
                     font_size, bold, italic, underline)

    def handle_error(self, message: str, detailed_error: str = None):
        """Handle errors with proper user feedback."""
        QMessageBox.critical(
            self,
            "Error",
            message + ("\n\nDetailed error:\n" + detailed_error if detailed_error else "")
        )
        logging.error(message + (f": {detailed_error}" if detailed_error else ""))

    def update_image_quality(self):
        try:
            # Update quality settings for all cells
            transform_mode = self.transform_combo.currentData()
            aspect_mode = self.aspect_combo.currentData()
            
            # Store current cursor
            current_cursor = self.cursor()
            self.setCursor(Qt.WaitCursor)
            
            # Batch update all cells
            for cell in self.collage.cells:
                if cell.pixmap:  # Only process cells with images
                    cell.transformation_mode = transform_mode
                    cell.aspect_ratio_mode = aspect_mode
                    if cell.original_pixmap:
                        # Regenerate scaled version from original
                        cell.pixmap = cell.original_pixmap
                    cell.update()
            
            # Restore cursor
            self.setCursor(current_cursor)
            
            logging.info("Image quality updated: transform=%s, aspect=%s",
                        self.transform_combo.currentText(),
                        self.aspect_combo.currentText())
                        
        except Exception as e:
            self.handle_error("Failed to update image quality", str(e))
            
    def closeEvent(self, event):
        """Handle application closure."""
        try:
            # Clean up any temporary files or resources
            for cell in self.collage.cells:
                if hasattr(cell, 'cleanup'):
                    cell.cleanup()
                    
            # Save application state/settings if needed
            logging.info("Application closing, cleanup complete")
            event.accept()
            
        except Exception as e:
            self.handle_error("Error during cleanup", str(e))

    def update_collage(self):
        rows = self.rows_spin.value()
        columns = self.cols_spin.value()
        logging.info("Actualizando collage: %d filas x %d columnas.", rows, columns)
        self.collage.update_grid(rows, columns)

    def save_collage(self):
        self.save_manager.save_collage(self.collage, self)

    def show_save_dialog(self):
        """Show advanced save dialog with preview and options."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Save Collage")
        dialog.setMinimumWidth(600)
        
        layout = QVBoxLayout(dialog)
        
        # Preview
        preview_label = QLabel()
        preview_pixmap = self.collage.grab().scaled(
            300, 300, 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        preview_label.setPixmap(preview_pixmap)
        layout.addWidget(preview_label, alignment=Qt.AlignCenter)
        
        # Format selection
        format_layout = QHBoxLayout()
        format_label = QLabel("Format:")
        format_combo = QComboBox()
        format_combo.addItems(["PNG", "JPEG", "WebP"])
        format_layout.addWidget(format_label)
        format_layout.addWidget(format_combo)
        layout.addLayout(format_layout)
        
        # Quality settings
        quality_layout = QHBoxLayout()
        quality_label = QLabel("Quality:")
        quality_slider = QSlider(Qt.Horizontal)
        quality_slider.setRange(1, 100)
        quality_slider.setValue(95)
        quality_value = QLabel("95%")
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(quality_slider)
        quality_layout.addWidget(quality_value)
        layout.addLayout(quality_layout)
        
        # Resolution multiplier
        resolution_layout = QHBoxLayout()
        resolution_label = QLabel("Resolution:")
        resolution_combo = QComboBox()
        resolution_combo.addItems(["1x", "2x", "4x"])
        resolution_layout.addWidget(resolution_label)
        resolution_layout.addWidget(resolution_combo)
        layout.addLayout(resolution_layout)
        
        # Connect quality slider to label
        quality_slider.valueChanged.connect(
            lambda v: quality_value.setText(f"{v}%")
        )
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.Accepted:
            return {
                'format': format_combo.currentText().lower(),
                'quality': quality_slider.value(),
                'resolution': int(resolution_combo.currentText()[0])
            }
        return None

    def optimize_for_format(self, pixmap: QPixmap, format: str, quality: int) -> QPixmap:
        """Optimize pixmap for specific output format."""
        if format in ['jpg', 'jpeg']:
            # Convert to RGB with white background for JPEG
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)
                
                # Use high-quality painter for conversion
                painter = QPainter(rgb_image)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(0, 0, image)
                painter.end()
                
                # Preserve DPI
                if hasattr(image, 'dotsPerMeterX'):
                    rgb_image.setDotsPerMeterX(image.dotsPerMeterX())
                    rgb_image.setDotsPerMeterY(image.dotsPerMeterY())
                
                return rgb_image
                
        elif format == 'webp':
            # Convert to ARGB32_Premultiplied for WebP
            if image.format() != QImage.Format_ARGB32_Premultiplied:
                return image.convertToFormat(
                    QImage.Format_ARGB32_Premultiplied,
                    Qt.NoOpaqueDetection
                )
        
        return image

# ========================================================
# Widget de cada celda del collage (cuadrada)
# ========================================================

class CollageCell(QWidget):
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap = None                # Display version of the image
        self.original_pixmap = None       # Original high-quality version
        self.original_image = None        # Store original QImage for maximum quality
        self.caption = ""                 # Text optional for the image
        self.use_caption_formatting = True  # Master flag for applying format
        self.caption_font_size = 14
        self.caption_bold = True
        self.caption_italic = False
        self.caption_underline = False
        self.transformation_mode = Qt.SmoothTransformation  # Default high quality transformation
        self.aspect_ratio_mode = Qt.KeepAspectRatio        # Default aspect ratio mode
        self.row_span = 1  # Number of rows this cell spans
        self.col_span = 1  # Number of columns this cell spans
        self.setAcceptDrops(True)
        self.setFixedSize(cell_size, cell_size)
        self.setStyleSheet("background-color: transparent;")
        self.selected = False  # Add selected state
        logging.info("Celda %d creada (tamaño %dx%d).", self.cell_id, cell_size, cell_size)

    def setSpan(self, row_span: int, col_span: int):
        """Set the cell's row and column span."""
        self.row_span = max(1, row_span)
        self.col_span = max(1, col_span)
        new_width = self.width() * self.col_span
        new_height = self.height() * self.row_span
        self.setFixedSize(new_width, new_height)
        self.update()
        logging.info(f"Cell {self.cell_id} span updated to {row_span}x{col_span}")

    def setImage(self, pixmap: QPixmap):
        """Set the image for this cell, preserving original quality."""
        # Store the original high quality version
        self.original_pixmap = pixmap
        # Create a display version
        self.pixmap = pixmap.copy()  # Make a copy for display
        self.update()
        logging.info("Cell %d: image loaded and original quality preserved.", self.cell_id)

    def clearImage(self):
        self.pixmap = None
        self.original_pixmap = None
        self.caption = ""
        self.update()

    def paintEvent(self, event):
        """Paint cell content with maximum quality preservation."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        rect = self.rect()
        
        # Draw selection border if selected
        if self.selected:
            pen = painter.pen()
            pen.setColor(QColor(52, 152, 219))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
            
            if any(c.selected for c in self.parent().cells if c != self):
                corner_size = 15
                pen.setColor(QColor(46, 204, 113))
                painter.setPen(pen)
                painter.drawLine(rect.left(), rect.top(), rect.left() + corner_size, rect.top())
                painter.drawLine(rect.left(), rect.top(), rect.left(), rect.top() + corner_size)
                painter.drawLine(rect.right(), rect.bottom(), rect.right() - corner_size, rect.bottom())
                painter.drawLine(rect.right(), rect.bottom(), rect.right(), rect.bottom() - corner_size)
        
        # Draw cell content
        if self.pixmap:
            # Use original high-quality pixmap if available
            source_pixmap = self.original_pixmap if hasattr(self, 'original_pixmap') and self.original_pixmap else self.pixmap
            
            # Scale with maximum quality preservation
            scaled = source_pixmap.scaled(
                rect.size(), 
                self.aspect_ratio_mode,
                Qt.SmoothTransformation  # Always use high quality transformation
            )
            
            # Center the image
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            target = QRect(x, y, scaled.width(), scaled.height())
            
            # Draw with quality preservation
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.drawPixmap(target, scaled, scaled.rect())
            
            # Draw caption if present
            if self.caption:
                self._render_high_quality_caption(painter, target)
                
        else:
            # Draw placeholder with better styling
            painter.fillRect(rect, QColor(245, 245, 245))
            painter.setPen(QColor(180, 180, 180))
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "Drop Image Here\nClick to Select")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() == Qt.ControlModifier:
                # Toggle selection with Ctrl+Click
                self.selected = not self.selected
                self.update()
                logging.info("Celda %d: selección cambiada a %s.", self.cell_id, self.selected)
            elif self.pixmap:
                # Original drag behavior only if there's an image
                logging.info("Celda %d: iniciando drag.", self.cell_id)
                drag = QDrag(self)
                mime_data = ImageMimeData(self.pixmap, self)
                drag.setMimeData(mime_data)
                preview = self.pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(preview)
                result = drag.exec(Qt.MoveAction)
                logging.info("Celda %d: drag finalizado (resultado: %s).", self.cell_id, result)

    def mouseDoubleClickEvent(self, event):
        # Permite editar el caption de la imagen
        if self.pixmap:
            new_caption, ok = QInputDialog.getText(self, "Editar Título", "Título de la imagen:", text=self.caption)
            if ok:
                self.caption = new_caption
                self.update()
                logging.info("Celda %d: caption actualizado a '%s'.", self.cell_id, self.caption)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        logging.info("Celda %d: dropEvent.", self.cell_id)
        mime = event.mimeData()
        # Caso 1: Intercambio interno
        if mime.hasFormat("application/x-pixmap"):
            source_cell = getattr(mime, "source_widget", None)
            if source_cell and source_cell is not self:
                logging.info("Celda %d: intercambiando imagen con Celda %d.", self.cell_id, source_cell.cell_id)
                self.pixmap, source_cell.pixmap = source_cell.pixmap, self.pixmap
                self.original_pixmap, source_cell.original_pixmap = source_cell.original_pixmap, self.original_pixmap
                self.caption, source_cell.caption = source_cell.caption, self.caption
                self.update()
                source_cell.update()
                event.acceptProposedAction()
                return
        # Caso 2: Cargar imagen externa
        elif mime.hasUrls():
            file_path = mime.urls()[0].toLocalFile()
            if file_path:
                self.loadExternalImage(file_path, event)
                return
        event.ignore()

    def loadExternalImage(self, file_path, event):
        """Load external image with maximum quality preservation."""
        try:
            logging.info("Cell %d: loading high-quality image from %s", self.cell_id, file_path)
            
            # Configure image reader for maximum quality
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)  # Apply EXIF orientation
            reader.setQuality(100)  # Maximum quality
            reader.setAllocationLimit(0)  # No memory limits for better quality
            
            # Get original image info
            original_size = reader.size()
            if not original_size.isValid():
                raise ValueError(f"Invalid image size: {reader.errorString()}")
            
            # Load image at original resolution
            original_image = reader.read()
            if original_image.isNull():
                raise ValueError(f"Failed to load image: {reader.errorString()}")
            
            # Store original DPI information
            dpmX = original_image.dotsPerMeterX()
            dpmY = original_image.dotsPerMeterY()
            
            # Convert to optimal format while preserving quality
            if original_image.format() != QImage.Format_ARGB32:
                original_image = original_image.convertToFormat(
                    QImage.Format_ARGB32,
                    Qt.NoOpaqueDetection  # Preserve alpha channel quality
                )
                # Restore original DPI
                original_image.setDotsPerMeterX(dpmX)
                original_image.setDotsPerMeterY(dpmY)
            
            # Create high-quality pixmap preserving all attributes
            self.original_pixmap = QPixmap.fromImage(original_image)
            self.original_image = original_image  # Keep original for quality preservation
            
            # Create optimized display version
            display_size = self.size()
            if original_size.width() > display_size.width() * 3 or original_size.height() > display_size.height() * 3:
                # Scale down for display while maintaining quality
                self.pixmap = self.original_pixmap.scaled(
                    display_size * 2,  # Keep 2x resolution for quality
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            else:
                # Use original size if not too large
                self.pixmap = self.original_pixmap.copy()
            
            # Cache the original high-quality version
            metadata = {
                'size': original_size,
                'format': reader.format().data().decode(),
                'dpm_x': dpmX,
                'dpm_y': dpmY,
                'timestamp': QFileInfo(file_path).lastModified()
            }
            image_cache.put(file_path, self.original_pixmap, metadata)
            
            self.update()
            event.acceptProposedAction()
            logging.info(f"Successfully loaded high-quality image in cell {self.cell_id}")
            
        except Exception as e:
            logging.error("Cell %d: Error loading image: %s", self.cell_id, str(e))
            event.ignore()

    def cleanup(self):
        """Clean up resources when cell is destroyed."""
        # Clear image data
        self.pixmap = None
        self.original_pixmap = None
        self.scaled_pixmap = None
        
        # Force garbage collection of large objects
        import gc
        gc.collect()

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()
        # Remove incorrect super().__del__() call since QWidget doesn't have a __del__ method

    def optimize_memory(self):
        """Optimize memory usage by clearing cached scaled images."""
        if hasattr(self, 'scaled_pixmap') and self.scaled_pixmap:
            self.scaled_pixmap = None
            gc.collect()  # Force garbage collection
        
        # Only keep high-quality original if needed
        if self.pixmap and self.original_pixmap:
            # Check if original is significantly larger than displayed size
            orig_size = self.original_pixmap.size()
            display_size = self.size()
            
            if (orig_size.width() > display_size.width() * 2 or 
                orig_size.height() > display_size.height() * 2):
                # Create an optimized version and release the original
                optimized = self.original_pixmap.scaled(
                    display_size * 2,  # Keep 2x resolution for zooming
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.original_pixmap = optimized
                gc.collect()
                
    def batch_process_images(self, image_paths: list):
        """Process multiple images efficiently."""
        for path in image_paths:
            try:
                # Check cache first
                cached_pixmap, metadata = image_cache.get(path)
                if cached_pixmap:
                    self.setImage(cached_pixmap)
                    continue
                
                # Load and process new image
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                
                # Get image info before loading
                size = reader.size()
                if size.width() > 4000 or size.height() > 4000:
                    # Scale down large images
                    scale = 4000 / max(size.width(), size.height())
                    reader.setScaledSize((size * scale).toSize())
                
                image = reader.read()
                if image.isNull():
                    raise ValueError(f"Failed to load image: {reader.errorString()}")
                
                # Convert to optimal format
                if image.format() != QImage.Format_ARGB32:
                    image = image.convertToFormat(QImage.Format_ARGB32)
                
                # Create pixmap and cache it
                pixmap = QPixmap.fromImage(image)
                metadata = {
                    'size': size,
                    'format': reader.format().data().decode(),
                    'timestamp': QFileInfo(path).lastModified()
                }
                image_cache.put(path, pixmap, metadata)
                
                self.setImage(pixmap)
                
            except Exception as e:
                logging.error(f"Error processing image {path}: {str(e)}")
                continue

    def _onImageLoaded(self, pixmap: QPixmap, filename: str):
        """Handle loaded image with quality preservation."""
        try:
        try:
            # Store original uncompressed image
            self.original_pixmap = pixmap.copy()  # Make a deep copy of original
            
            # Create display version at cell size while maintaining quality
            display_pixmap = pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Set the display version
            self.setImage(display_pixmap)
            
            # Cache the original high-quality version
            metadata = ImageOptimizer.process_metadata(filename)
            image_cache.put(filename, self.original_pixmap, metadata)
            
            # Close progress dialog if exists
            if hasattr(self, 'progress'):
                self.progress.close()
                delattr(self, 'progress')
                
            # Clean up the loader thread
            if hasattr(self, 'loader'):
                self.loader.deleteLater()
                delattr(self, 'loader')
            
            logging.info(f"Cell {self.cell_id}: Image loaded at original quality")
            
        except Exception as e:
            logging.error(f"Cell {self.cell_id}: Error in image loading: {str(e)}")
            if hasattr(self, 'progress'):
                self.progress.close()
                delattr(self, 'progress')

    def render_high_quality(self, painter: QPainter):
        """Render cell at maximum quality for saving."""
        if not self.pixmap:
            return
            
        rect = self.rect()
        pos = self.mapTo(self.parent(), QPoint(0, 0))
        target_rect = QRect(pos, rect.size())
        
        # Use original high-quality pixmap if available, fall back to regular pixmap if not
        source_pixmap = getattr(self, 'original_pixmap', None) or self.pixmap
        
        # Configure device pixel ratio for high DPI support
        if hasattr(source_pixmap, 'devicePixelRatio'):
            source_pixmap.setDevicePixelRatio(1.0)  # Ensure 1:1 pixel mapping
        
        painter.save()
        # Enable all quality-related render hints
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        # Scale image while preserving aspect ratio and maximum quality
        scaled_pixmap = source_pixmap.scaled(
            target_rect.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Center the image in the cell
        x = target_rect.x() + (target_rect.width() - scaled_pixmap.width()) // 2
        y = target_rect.y() + (target_rect.height() - scaled_pixmap.height()) // 2
        
        # Draw using composition mode that preserves quality
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(x, y, scaled_pixmap)
        
        # Draw caption with optimal quality if present
        if self.caption:
            self._render_high_quality_caption(painter, QRect(x, y, scaled_pixmap.width(), scaled_pixmap.height()))
        
        painter.restore()
        
    def _render_high_quality_caption(self, painter: QPainter, image_rect: QRect):
        """Render caption with maximum quality."""
        font = painter.font()
        if self.use_caption_formatting:
            font.setPointSize(self.caption_font_size)
            font.setBold(self.caption_bold)
            font.setItalic(self.caption_italic)
            font.setUnderline(self.caption_underline)
            # Enable kerning and other font optimizations
            font.setKerning(True)
            font.setHintingPreference(QFont.PreferFullHinting)
        painter.setFont(font)
        
        # Calculate optimal text positioning
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(self.caption)
        text_rect.moveCenter(QPoint(
            image_rect.center().x(),
            image_rect.bottom() - text_rect.height()//2 - 5
        ))
        
        # Draw high-quality text background
        background_rect = text_rect.adjusted(-6, -3, 6, 3)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.fillRect(background_rect, QColor(0, 0, 0, 160))
        
        # Draw text with high-quality anti-aliasing
        painter.setPen(QColor(0, 0, 0, 160))  # Shadow
        painter.drawText(text_rect.adjusted(1, 1, 1, 1), Qt.AlignCenter, self.caption)
        painter.setPen(Qt.white)  # Main text
        painter.drawText(text_rect, Qt.AlignCenter, self.caption)

    def getHighQualityRendering(self) -> QPixmap:
        """Get a high quality rendered version of the cell content."""
        if not self.pixmap:
            return None
            
        # Always use original high-quality pixmap if available
        source_pixmap = self.original_pixmap if hasattr(self, 'original_pixmap') and self.original_pixmap else self.pixmap
        
        # Create target pixmap at desired size
        target_size = self.size()
        output = QPixmap(target_size)
        output.fill(Qt.transparent)
        
        # Set up painter with maximum quality settings
        painter = QPainter(output)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        # Calculate scaling while preserving aspect ratio
        source_rect = source_pixmap.rect()
        target_rect = self.rect()
        
        # Scale and center the image
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(target_rect.size(), Qt.KeepAspectRatio)
            x = (target_rect.width() - scaled_size.width()) // 2
            y = (target_rect.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw with maximum quality
        painter.drawPixmap(target_rect, source_pixmap, source_rect)
        
        # Draw caption if present
        if self.caption:
            self._render_high_quality_caption(painter, target_rect)
        
        painter.end()
        return output
        
    def _create_high_quality_pixmap(self, size: QSize) -> QPixmap:
        """Create a high quality scaled version of the image."""
        if not self.original_pixmap:
            return None
            
        # Create intermediate high-resolution pixmap
        intermediate_size = size * 2  # Work at 2x target size for better quality
        intermediate = QPixmap(intermediate_size)
        intermediate.fill(Qt.transparent)
        
        # High quality painting
        painter = QPainter(intermediate)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Scale while preserving aspect ratio
        source_rect = self.original_pixmap.rect()
        target_rect = QRect(QPoint(0, 0), intermediate_size)
        
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(intermediate_size, Qt.KeepAspectRatio)
            x = (intermediate_size.width() - scaled_size.width()) // 2
            y = (intermediate_size.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw at high resolution
        painter.drawPixmap(target_rect, self.original_pixmap, source_rect)
        painter.end()
        
        # Scale down to target size with high quality
        return intermediate.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _preserve_image_attributes(self, image: QImage, source_image: QImage = None) -> QImage:
        """Preserve image attributes during transformations."""
        if source_image and hasattr(source_image, 'dotsPerMeterX'):
            # Preserve DPI information
            image.setDotsPerMeterX(source_image.dotsPerMeterX())
            image.setDotsPerMeterY(source_image.dotsPerMeterY())
        
        # Ensure optimal color space
        if image.format() != QImage.Format_ARGB32_Premultiplied:
            image = image.convertToFormat(
                QImage.Format_ARGB32_Premultiplied,
                Qt.NoOpaqueDetection  # Preserve alpha channel quality
            )
        
        return image
        
    def scale_with_quality(self, pixmap: QPixmap, target_size: QSize, keep_attributes: bool = True) -> QPixmap:
        """Scale image while preserving maximum quality."""
        if not pixmap:
            return None
            
        # Work at 2x target size for better quality during scaling
        intermediate_size = target_size * 2
        
        # Create intermediate high-resolution pixmap
        intermediate = QPixmap(intermediate_size)
        intermediate.fill(Qt.transparent)
        
        # High quality painting to intermediate
        painter = QPainter(intermediate)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        # Draw at high resolution
        source_rect = pixmap.rect()
        target_rect = QRect(QPoint(0, 0), intermediate_size)
        
        if self.aspect_ratio_mode == Qt.KeepAspectRatio:
            scaled_size = source_rect.size().scaled(intermediate_size, Qt.KeepAspectRatio)
            x = (intermediate_size.width() - scaled_size.width()) // 2
            y = (intermediate_size.height() - scaled_size.height()) // 2
            target_rect = QRect(QPoint(x, y), scaled_size)
        
        # Draw original image to intermediate
        painter.drawPixmap(target_rect, pixmap, source_rect)
        painter.end()
        
        # Convert to image for attribute preservation if needed
        if keep_attributes:
            intermediate_image = intermediate.toImage()
            source_image = pixmap.toImage()
            intermediate_image = self._preserve_image_attributes(intermediate_image, source_image)
            intermediate = QPixmap.fromImage(intermediate_image)
        
        # Scale down to final size with high quality
        result = intermediate.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Final attribute preservation if needed
        if keep_attributes:
            result_image = result.toImage()
            result_image = self._preserve_image_attributes(result_image, source_image)
            result = QPixmap.fromImage(result_image)
        
        return result

class SaveManager:
    """Manages save operations with proper resource handling."""
    
    def __init__(self):
        self.quality_manager = QualitySettingsManager()
        self.dpi_manager = DPIManager()
        self.color_manager = ColorProfileManager()
        self.format_handler = OutputFormatHandler()
        
    def save_collage(self, collage_widget: 'CollageWidget', parent_window: QWidget = None) -> bool:
        """Save collage with maximum quality and proper resource management."""
        painter = None
        try:
            # Create high-resolution output with 4x scale
            scale_factor = 4.0
            collage_size = collage_widget.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Create output image with optimal settings
            output_image = QImage(scaled_size, QImage.Format_ARGB32_Premultiplied)
            output_image.fill(Qt.transparent)
            
            # Set high DPI (300 DPI)
            output_image.setDotsPerMeterX(11811)  # 300 DPI
            output_image.setDotsPerMeterY(11811)  # 300 DPI
            
            # Create high-res pixmap
            high_res_pixmap = QPixmap.fromImage(output_image)
            
            # Configure painter for maximum quality
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Scale while painting with quality preservation
            painter.scale(scale_factor, scale_factor)
            
            # Render with maximum quality
            collage_widget.render(painter, QPoint(0, 0), collage_widget.rect())
            painter.end()
            painter = None

            # Get save path from user
            file_path, selected_filter = QFileDialog.getSaveFileName(
                parent_window,
                "Save Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Save cancelled by user")
                return False
                
            # Add appropriate extension
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default to PNG for best quality
            
            # Get format and optimize
            format = file_path.split('.')[-1].lower()
            optimized_pixmap = self.format_handler.optimize_for_output(high_res_pixmap, format)
            
            # Save with optimal settings
            if not self.format_handler.save_with_optimal_settings(optimized_pixmap, file_path, format):
                raise IOError(f"Failed to save image as {format.upper()}")
            
            logging.info("Collage saved successfully to %s", file_path)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Collage saved successfully!")
            msg.setDetailedText(
                f"Format: {format.upper()}\n"
                f"Quality: {quality}%\n"
                f"Resolution: {scale}x\n"
                f"Size: {scaled_size.width()}x{scaled_size.height()}\n"
                f"Location: {file_path}"
            )
            msg.exec_()
            return True
            
        except Exception as e:
            logging.error("Error saving collage: %s", e)
            if parent_window:
                QMessageBox.critical(
                    parent_window,
                    "Save Error",
                    f"Failed to save collage: {str(e)}"
                )
            return False
            
        finally:
            # Ensure proper cleanup
            if painter and painter.isActive():
                try:
                    painter.end()
                except:
                    pass

# ========================================================
# Punto de Entrada
# ========================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
