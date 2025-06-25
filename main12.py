import sys
import logging
import traceback
import os
import json
import glob
import gc
from typing import Optional

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
from PySide6.QtGui import QDrag, QPixmap, QPainter, QImageReader, QColor, QShortcut, QImage, QKeySequence

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logging.warning("psutil not available, memory monitoring will be limited")

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
    logging.error("Uncaught exception", exc_info=(exctype, value, traceback))
    sys.__excepthook__(exctype, value, traceback)

sys.excepthook = global_exception_handler

# ========================================================
# Sistema de caché de imágenes
# ========================================================


class ImageCache:
    """Cache system for optimizing image loading and processing."""
    def __init__(self):
        self.cache = {}
        self.max_size = 50  # Maximum number of images to cache
        self._cleanup_threshold = 0.8  # Cleanup when cache is 80% full

    def get(self, key: str) -> tuple[QPixmap, dict]:
        """Get an image and its metadata from cache."""
        return self.cache.get(key, (None, None))

    def put(self, key: str, pixmap: QPixmap, metadata: dict):
        """Store an image and its metadata in cache."""
        if len(self.cache) >= self.max_size * self._cleanup_threshold:
            self._cleanup()
        self.cache[key] = (pixmap, metadata)

    def _cleanup(self):
        """Remove least recently used items from cache."""
        if len(self.cache) > self.max_size / 2:
            # Remove oldest third of entries
            remove_count = len(self.cache) // 3
            keys = list(self.cache.keys())
            for key in keys[:remove_count]:
                del self.cache[key]

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
        stream = QDataStream(ba, QIODevice.WriteOnly)
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
        """Optimize image for display while maintaining quality."""
        # Convert to optimal format if needed
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        
        # Calculate optimal size
        max_dimension = max(target_size.width(), target_size.height())
        if max_dimension > 2000:
            scale = 2000 / max_dimension
            target_size *= scale
        
        # Scale image if needed
        if image.size() != target_size:
            image = image.scaled(
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        
        return image

    @staticmethod
    def process_metadata(file_path: str) -> dict:
        """Extract and process image metadata."""
        reader = QImageReader(file_path)
        return {
            'size': reader.size(),
            'format': reader.format().data().decode(),
            'depth': reader.imageFormat(),
            'supported': reader.canRead(),
            'timestamp': QFileInfo(file_path).lastModified()
        }

# ========================================================
# Widget de cada celda del collage (cuadrada)
# ========================================================

class CollageCell(QWidget):
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap = None                # Imagen cargada
        self.original_pixmap = None       # Guardamos la imagen original en alta calidad
        self.caption = ""                 # Texto opcional para la imagen
        self.use_caption_formatting = True  # Flag maestro para aplicar formato
        # Valores por defecto para el formato personalizado
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
        self.original_pixmap = pixmap  # Store original high quality version
        self.pixmap = pixmap
        self.update()
        logging.info("Celda %d: imagen cargada.", self.cell_id)

    def clearImage(self):
        self.pixmap = None
        self.original_pixmap = None
        self.caption = ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        
        rect = self.rect()
        
        # Draw selection border if selected
        if self.selected:
            # Create a more visible selection effect
            pen = painter.pen()
            pen.setColor(QColor(52, 152, 219))  # Nice blue color
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
            
            # Add diagonal lines in corners to indicate mergeability
            if any(c.selected for c in self.parent().cells if c != self):
                corner_size = 15
                pen.setColor(QColor(46, 204, 113))  # Green color for merge hint
                painter.setPen(pen)
                # Top-left corner
                painter.drawLine(rect.left(), rect.top(), rect.left() + corner_size, rect.top())
                painter.drawLine(rect.left(), rect.top(), rect.left(), rect.top() + corner_size)
                # Bottom-right corner
                painter.drawLine(rect.right(), rect.bottom(), rect.right() - corner_size, rect.bottom())
                painter.drawLine(rect.right(), rect.bottom(), rect.right(), rect.bottom() - corner_size)
        
        # Draw split indicator for merged cells
        if self.row_span > 1 or self.col_span > 1:
            pen = painter.pen()
            pen.setColor(QColor(155, 89, 182))  # Purple color for split hint
            pen.setStyle(Qt.DashLine)
            pen.setWidth(1)
            painter.setPen(pen)
            
            # Draw dashed lines to indicate split points
            cell_width = rect.width() / self.col_span
            cell_height = rect.height() / self.row_span
            
            # Vertical split lines
            for i in range(1, self.col_span):
                x = rect.left() + cell_width * i
                painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
                
            # Horizontal split lines
            for i in range(1, self.row_span):
                y = rect.top() + cell_height * i
                painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        # Draw cell content
        if self.pixmap:
            # Scale and center the image with better quality
            scaled = self.pixmap.scaled(
                rect.size(), 
                self.aspect_ratio_mode,
                self.transformation_mode
            )
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            target = QRect(x, y, scaled.width(), scaled.height())
            painter.drawPixmap(target, scaled, scaled.rect())
            
            if self.caption:
                # Configure caption font
                font = painter.font()
                if self.use_caption_formatting:
                    font.setPointSize(self.caption_font_size)
                    font.setBold(self.caption_bold)
                    font.setItalic(self.caption_italic)
                    font.setUnderline(self.caption_underline)
                else:
                    font.setPointSize(12)
                painter.setFont(font)
                
                # Draw caption with better visibility
                metrics = painter.fontMetrics()
                text_rect = metrics.boundingRect(self.caption)
                text_rect.moveCenter(QPoint(rect.center().x(), rect.bottom() - text_rect.height()//2 - 5))
                background_rect = text_rect.adjusted(-6, -3, 6, 3)
                
                # Draw semi-transparent background
                painter.fillRect(background_rect, QColor(0, 0, 0, 160))
                
                # Draw text with subtle shadow for better readability
                painter.setPen(QColor(0, 0, 0, 160))
                painter.drawText(text_rect.adjusted(1, 1, 1, 1), Qt.AlignCenter, self.caption)
                painter.setPen(Qt.white)
                painter.drawText(text_rect, Qt.AlignCenter, self.caption)
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
        try:
            logging.info("Celda %d: cargando imagen desde %s", self.cell_id, file_path)
            
            # Check cache first
            cached_pixmap, metadata = image_cache.get(file_path)
            if cached_pixmap:
                self.setImage(cached_pixmap)
                event.acceptProposedAction()
                logging.info(f"Loaded image from cache for cell {self.cell_id}")
                return
            
            reader = QImageReader(file_path)
            
            # Configure image reader for optimal loading
            reader.setAutoTransform(True)  # Apply EXIF orientation
            reader.setQuality(100)  # Use maximum quality for all formats
            
            # Get image info before loading
            size = reader.size()
            img_format = reader.format().data().decode()
            
            # Log image details
            logging.info(f"Image details - Size: {size.width()}x{size.height()}, Format: {img_format}")
            
            # Check if format is supported
            supported_formats = ['png', 'jpg', 'jpeg', 'bmp', 'webp', 'gif', 'tiff']
            if img_format.lower() not in supported_formats:
                # Try to convert unsupported format
                temp_image = QImage(file_path)
                if not temp_image.isNull():
                    # Save as PNG temporarily
                    temp_file = f"{file_path}.png"
                    temp_image.save(temp_file, "PNG")
                    reader = QImageReader(temp_file)
                    import os
                    os.remove(temp_file)  # Clean up
                else:
                    raise ValueError(f"Unsupported image format: {img_format}")
            
            # Handle large images
            max_dimension = 4000  # Increased max dimension for high-quality images
            if size.width() > max_dimension or size.height() > max_dimension:
                scale_factor = max_dimension / max(size.width(), size.height())
                new_size = size * scale_factor
                reader.setScaledSize(new_size.toSize())
                logging.info(f"Large image detected, scaling to {new_size.width()}x{new_size.height()}")
            
            # Load the image
            image = reader.read()
            if image.isNull():
                error = reader.errorString()
                raise ValueError(f"Failed to load image: {error}")
            
            # Optimize image
            optimized_image = ImageOptimizer.optimize_image(image, self.size())
            
            # Create pixmap and store it
            pixmap = QPixmap.fromImage(optimized_image)
            self.setImage(pixmap)
            
            # Cache the image
            metadata = ImageOptimizer.process_metadata(file_path)
            image_cache.put(file_path, pixmap, metadata)
            
            # Accept the drop event
            event.acceptProposedAction()
            logging.info(f"Successfully loaded image in cell {self.cell_id}")
            
        except Exception as e:
            logging.error("Celda %d: Error al cargar la imagen: %s", self.cell_id, str(e))
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

        # Create set of selected positions for validation
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
        
        anim1.setPixmap(source_cell.pixmap.scaled(source_cell.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if target_cell.pixmap:
            anim2.setPixmap(target_cell.pixmap.scaled(target_cell.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
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
        animation_group.addAnimation(anim1_pos)

        if target_cell.pixmap:
            anim2_pos = QPropertyAnimation(anim2, b"geometry")
            anim2_pos.setDuration(300)
            anim2_pos.setStartValue(QRect(target_pos, target_cell.size()))
            anim2_pos.setEndValue(QRect(source_pos, source_cell.size()))
            anim2_pos.setEasingCurve(QEasingCurve.InOutCubic)
            animation_group.addAnimation(anim2_pos)

        animation_group.finished.connect(lambda: self.cleanup_animation(anim1, anim2))

        # Start animation
        animation_group.start(QAbstractAnimation.DeleteWhenStopped)

    def cleanup_animation(self, anim1: QLabel, anim2: QLabel):
        """Clean up animation widgets after animation completes."""
        if anim1:
            anim1.deleteLater()
        if anim2:
            anim2.deleteLater()

    def sanitize_cell_positions(self):
        """Ensure all cells have correct positions in the grid layout."""
        current_positions = set()
        cells_to_fix = []
        
        # First pass: collect current positions and cells that need fixing
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and isinstance(item.widget(), CollageCell):
                cell = item.widget()
                pos = self.grid_layout.getItemPosition(i)
                if pos:
                    row, col, row_span, col_span = pos
                    # Store actual position and spans
                    cell.row_span = row_span
                    cell.col_span = col_span
                    current_positions.add((row, col))
                    
        # Second pass: fix any invalid positions
        for cell in self.cells[:]:  # Work on a copy of the list
            pos = self.get_cell_position(cell)
            if not pos or pos not in current_positions:
                # Remove from layout and list
                self.grid_layout.removeWidget(cell)
                if cell in self.cells:
                    self.cells.remove(cell)
                cell.hide()
                cell.deleteLater()
                
        # Update layout
        self.grid_layout.update()

# ========================================================
# Undo Stack and related classes
# ========================================================

class UndoCommand:
    """Base class for undoable commands."""
    def undo(self):
        pass

    def redo(self):
        pass

class ImageSwapCommand(UndoCommand):
    def __init__(self, source_cell, target_cell):
        self.source_cell = source_cell
        self.target_cell = target_cell
        self.source_pixmap = source_cell.pixmap
        self.source_caption = source_cell.caption
        self.target_pixmap = target_cell.pixmap
        self.target_caption = target_cell.caption

    def undo(self):
        self.source_cell.pixmap = self.source_pixmap
        self.source_cell.caption = self.source_caption
        self.target_cell.pixmap = self.target_pixmap
        self.target_cell.caption = self.target_caption
        self.source_cell.update()
        self.target_cell.update()

    def redo(self):
        self.source_cell.pixmap = self.target_pixmap
        self.source_cell.caption = self.target_caption
        self.target_cell.pixmap = self.source_pixmap
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
    """Worker thread for loading and processing images."""
    finished = Signal(QPixmap, str)  # Emits processed pixmap and filename
    error = Signal(str)  # Emits error message if loading fails
    progress = Signal(int)  # Emits progress percentage
    
    def __init__(self, file_paths, target_size=None):
        super().__init__()
        self.file_paths = file_paths if isinstance(file_paths, list) else [file_paths]
        self.target_size = target_size
        self._cancel = False
        
    def run(self):
        """Process images in a separate thread."""
        try:
            total = len(self.file_paths)
            for i, file_path in enumerate(self.file_paths):
                if self._cancel:
                    return
                    
                # Calculate progress
                progress = int((i / total) * 100)
                self.progress.emit(progress)
                
                # Load and process image
                reader = QImageReader(file_path)
                reader.setAutoTransform(True)
                
                if self.target_size:
                    reader.setScaledSize(self.target_size)
                    
                image = reader.read()
                if image.isNull():
                    self.error.emit(f"Failed to load {file_path}: {reader.errorString()}")
                    continue
                    
                # Optimize image
                if self.target_size:
                    image = ImageOptimizer.optimize_image(image, self.target_size)
                    
                # Convert to pixmap and emit
                pixmap = QPixmap.fromImage(image)
                self.finished.emit(pixmap, file_path)
                
            # Final progress update
            self.progress.emit(100)
            
        except Exception as e:
            self.error.emit(str(e))
            
    def cancel(self):
        """Cancel the current operation."""
        self._cancel = True

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

class ErrorRecoveryManager:
    """Manages application error recovery."""
    def __init__(self, parent):
        self.parent = parent
        self.error_count = 0
        self.last_error_time = QDateTime.currentDateTime()
        self.error_threshold = 5  # Max errors before recovery action
        self.error_window = 300  # 5 minutes window for error counting
        
    def handle_error(self, error: Exception, context: str):
        """Handle errors and perform recovery if needed."""
        current_time = QDateTime.currentDateTime()
        
        # Reset error count if outside window
        if self.last_error_time.secsTo(current_time) > self.error_window:
            self.error_count = 0
            
        self.error_count += 1
        self.last_error_time = current_time
        
        # Log error
        logging.error(f"Error in {context}: {str(error)}\n{traceback.format_exc()}")
        
        # Check if recovery action needed
        if self.error_count >= self.error_threshold:
            self.perform_recovery()
            
    def perform_recovery(self):
        """Perform recovery actions."""
        try:
            # Save current state
            state = self.parent.get_collage_state()
            recovery_file = os.path.join(
                self.parent.autosave_manager.autosave_path,
                f"recovery_{QDateTime.currentDateTime().toString('yyyyMMdd_hhmmss')}.json"
            )
            with open(recovery_file, 'w') as f:
                json.dump(state, f)
            
            # Clear problematic state
            self.parent.collage.populate_grid()  # Reset grid
            image_cache.cache.clear()  # Clear image cache
            gc.collect()  # Force garbage collection
            
            # Reset error count
            self.error_count = 0
            
            # Notify user
            QMessageBox.warning(
                self.parent,
                "Application Recovery",
                "The application has been reset due to multiple errors.\n"
                "Your previous state has been saved and can be restored."
            )
            
            logging.info("Recovery performed successfully")
            
        except Exception as e:
            logging.critical(f"Recovery failed: {str(e)}")
            QMessageBox.critical(
                self.parent,
                "Critical Error",
                "Recovery failed. It is recommended to restart the application."
            )

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
        self.transform_combo.addItem("High Quality", Qt.SmoothTransformation)
        self.transform_combo.addItem("Balanced", Qt.SmoothTransformation)
        self.transform_combo.addItem("Fast", Qt.FastTransformation)
        self.transform_combo.setCurrentIndex(0)
        self.transform_combo.currentIndexChanged.connect(self.update_image_quality)
        self.transform_combo.setToolTip("Select image transformation quality")
        
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
                for (mr, mc), (mrs, mcs) in self.collage.merged_cells.items():
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
            event.ignore()  # Prevent closure if cleanup failed

    def update_collage(self):
        rows = self.rows_spin.value()
        columns = self.cols_spin.value()
        logging.info("Actualizando collage: %d filas x %d columnas.", rows, columns)
        self.collage.update_grid(rows, columns)

    def save_collage(self):
        logging.info("Guardando collage...")
        try:
            # Crear un QPixmap del tamaño del collage con mayor resolución para mejor calidad
            scale_factor = 2.0  # Duplicar la resolución al guardar
            collage_size = self.collage.size()
            scaled_size = QSize(int(collage_size.width() * scale_factor), 
                              int(collage_size.height() * scale_factor))
            
            # Crear un pixmap de alta resolución
            high_res_pixmap = QPixmap(scaled_size)
            high_res_pixmap.fill(Qt.transparent)
            
            # Pintar el collage en alta resolución
            painter = QPainter(high_res_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            
            # Escalar mientras dibujamos
            painter.scale(scale_factor, scale_factor)
            
            # Corrección: Usar render con los parámetros adecuados (origen y región)
            self.collage.render(painter, QPoint(0, 0), self.collage.rect())
            
            painter.end()

            file_path, selected_filter = QFileDialog.getSaveFileName(
                self,
                "Guardar Collage",
                "",
                "PNG Files (*.png);;JPEG Files (*.jpg);;WebP Files (*.webp)"
            )
            
            if not file_path:
                logging.info("Guardado cancelado por el usuario.")
                return
                
            if not (file_path.lower().endswith(".png") or 
                    file_path.lower().endswith(".jpg") or 
                    file_path.lower().endswith(".jpeg") or
                    file_path.lower().endswith(".webp")):
                # Agregar extensión según el filtro seleccionado
                if "PNG" in selected_filter:
                    file_path += ".png"
                elif "JPEG" in selected_filter or "JPG" in selected_filter:
                    file_path += ".jpg"
                elif "WebP" in selected_filter:
                    file_path += ".webp"
                else:
                    file_path += ".png"  # Default
            
            # Configurar calidad según el formato
            fmt_ext = file_path.split('.')[-1].lower()
            quality = 100  # Máxima calidad por defecto

            if fmt_ext in ['jpg', 'jpeg']:
                if not high_res_pixmap.save(file_path, fmt_ext, quality):
                    raise IOError("No se pudo guardar la imagen JPEG.")
            elif fmt_ext == 'webp':
                if not high_res_pixmap.save(file_path, fmt_ext, quality):
                    raise IOError("No se pudo guardar la imagen WebP.")
            else:  # png y otros
                if not high_res_pixmap.save(file_path):
                    raise IOError("No se pudo guardar la imagen.")
                    
            logging.info("Collage guardado en %s con alta calidad", file_path)
            
        except Exception as e:
            logging.error("Se produjo un error al guardar el collage: %s\n%s", e, traceback.format_exc())

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

    def optimize_for_format(self, pixmap: QPixmap, fmt: str, quality: int) -> QPixmap:
        """Optimize pixmap for specific output format."""
        if fmt in ['jpg', 'jpeg']:
            # Convert to RGB for JPEG (removes alpha channel)
            image = pixmap.toImage()
            if image.hasAlphaChannel():
                rgb_image = QImage(image.size(), QImage.Format_RGB32)
                rgb_image.fill(Qt.white)  # White background
                painter = QPainter(rgb_image)
                painter.drawImage(0, 0, image)
                painter.end()
                return QPixmap.fromImage(rgb_image)
        elif fmt == 'webp':
            # WebP supports transparency and compression
            return pixmap
        # PNG doesn't need special handling
        return pixmap

    def save_collage_with_options(self, options: dict):
        """Save collage with advanced options."""
        try:
            fmt = options['format']
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
            
            # Scale while painting
            painter.scale(scale, scale)
            self.collage.render(painter)
            painter.end()
            
            # Get save path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Collage",
                "",
                f"{fmt.upper()} Files (*.{fmt})"
            )
            
            if not file_path:
                return
                
            # Ensure correct extension
            if not file_path.lower().endswith(f".{fmt}"):
                file_path += f".{fmt}"
            
            # Optimize for format
            final_pixmap = self.optimize_for_format(output_pixmap, fmt, quality)
            
            # Save with format-specific settings
            success = final_pixmap.save(
                file_path,
                fmt,
                quality if fmt != 'png' else -1  # PNG uses lossless compression
            )
            
            if success:
                logging.info(f"Collage saved successfully to {file_path}")
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("Collage saved successfully!")
                msg.setDetailedText(
                    f"Format: {fmt.upper()}\n"
                    f"Quality: {quality}%\n"
                    f"Resolution: {scale}x\n"
                    f"Size: {output_size.width()}x{output_size.height()}\n"
                    f"Location: {file_path}"
                )
                msg.exec_()
            else:
                raise IOError(f"Failed to save image as {fmt.upper()}")
                
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
