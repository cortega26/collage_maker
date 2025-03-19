"""
Collage Maker - A PySide6 application to create and manage image collages.
Improvements include drag/drop reordering, saving collages, responsive grid updates,
and optional captions for each image. The caption formatting (font size, bold, italic,
color, and underlined) is fully configurable via the control panel.

Features:
- Drag and drop images from file system
- Rearrange images by dragging between cells
- Add captions to images with customizable formatting
- Adjustable grid layout (rows and columns)
- Save collage as an image file (PNG/JPEG)
"""

import sys
import os
import logging
import traceback
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QSpinBox,
    QHBoxLayout, QPushButton, QFileDialog, QInputDialog, QCheckBox, QLabel,
    QColorDialog, QMessageBox, QProgressDialog, QSizePolicy, QFrame
)
from PySide6.QtCore import (
    Qt, QMimeData, QByteArray, QDataStream, QIODevice, QRect, QSize, QPoint,
    Signal, QThread, QSettings, QDir
)
from PySide6.QtGui import (
    QDrag, QPixmap, QPainter, QImageReader, QColor, QFont, QImage, QFontMetrics,
    QPalette, QIcon
)

# Application constants
APP_NAME = "Collage Maker"
APP_VERSION = "1.0.1"
DEFAULT_CELL_SIZE = 260
DEFAULT_SPACING = 2
DEFAULT_ROWS = 2
DEFAULT_COLUMNS = 2
DEFAULT_CAPTION_SIZE = 14
MAX_CELL_SIZE = 500
MIN_CELL_SIZE = 100
MAX_ROWS = 10
MAX_COLUMNS = 10
MAX_IMAGE_DIMENSION = 2000  # Maximum dimension for loaded images
VALID_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(
            os.path.expanduser("~"), 
            "collage_maker.log"
        ))
    ]
)
logger = logging.getLogger("CollageMaker")

# Add exception hook for uncaught exceptions
def exception_hook(exctype, value, traceback_obj):
    """Global exception hook to log uncaught exceptions."""
    logger.critical(
        "Uncaught exception",
        exc_info=(exctype, value, traceback_obj)
    )
    sys.__excepthook__(exctype, value, traceback_obj)

sys.excepthook = exception_hook


class ImageLoadWorker(QThread):
    """Worker thread for loading images asynchronously."""
    finished = Signal(object, str)
    error = Signal(str)
    progress = Signal(int)  # New signal for progress updates
    
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.canceled = False
        
    def cancel(self):
        """Cancel the current operation."""
        self.canceled = True
        
    def run(self):
        try:
            if self.canceled:
                return
                
            reader = QImageReader(self.file_path)
            reader.setAutoTransform(True)  # Apply EXIF rotation
            
            # Check image format
            if not reader.canRead():
                error_message = f"Cannot read image format: {reader.errorString()}"
                logger.error(error_message)
                self.error.emit(error_message)
                return
                
            # Get image size for large image optimization
            size = reader.size()
            if size.width() > 2000 or size.height() > 2000:
                reader.setScaledSize(QSize(2000, 2000))
                
            # Load the image
            image = reader.read()
            
            if self.canceled:
                return
                
            if image.isNull():
                error_message = f"Failed to load image: {reader.errorString()}"
                logger.error(error_message)
                self.error.emit(error_message)
                return
                
            pixmap = QPixmap.fromImage(image)
            self.finished.emit(pixmap, os.path.basename(self.file_path))
        except Exception as e:
            if not self.canceled:
                error_message = f"Error loading image {self.file_path}: {str(e)}"
                logger.error(f"{error_message}\n{traceback.format_exc()}")
                self.error.emit(error_message)


class CaptionFormatting:
    """Container for caption formatting properties with improved serialization."""
    def __init__(self):
        self.enabled = True
        self.font_size = DEFAULT_CAPTION_SIZE
        self.bold = True
        self.italic = True
        self.underline = True
        self.color = QColor(255, 255, 0)  # Default to yellow
        
    def apply_to_font(self, font: QFont) -> QFont:
        """Apply formatting settings to the provided font."""
        if not self.enabled:
            return font
            
        font.setPointSize(self.font_size)
        font.setBold(self.bold)
        font.setItalic(self.italic)
        font.setUnderline(self.underline)
        return font
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert formatting to a dictionary for saving."""
        return {
            'enabled': self.enabled,
            'font_size': self.font_size,
            'bold': self.bold,
            'italic': self.italic,
            'underline': self.underline,
            'color': self.color.name()
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CaptionFormatting':
        """Create a CaptionFormatting instance from a dictionary."""
        formatting = cls()
        
        # Use more robust attribute setting
        if 'enabled' in data:
            formatting.enabled = bool(data['enabled'])
            
        if 'font_size' in data:
            try:
                size = int(data['font_size'])
                if 8 <= size <= 36:
                    formatting.font_size = size
            except (ValueError, TypeError):
                pass
                
        if 'bold' in data:
            formatting.bold = bool(data['bold'])
            
        if 'italic' in data:
            formatting.italic = bool(data['italic'])
            
        if 'underline' in data:
            formatting.underline = bool(data['underline'])
            
        if 'color' in data:
            try:
                color = QColor(data['color'])
                if color.isValid():
                    formatting.color = color
            except:
                pass  # Keep default color if invalid
                
        return formatting


class ImageMimeData(QMimeData):
    """Custom MIME data for image drag operations with source tracking."""
    
    def __init__(self, pixmap: QPixmap, source_widget: 'CollageCell'):
        """
        Initialize with the image pixmap and source widget reference.
        
        Args:
            pixmap: The image pixmap to drag
            source_widget: The source cell widget
        """
        super().__init__()
        self._pixmap = pixmap
        self._source_widget = source_widget
        
        # Serialize the pixmap into a byte array
        ba = QByteArray()
        stream = QDataStream(ba, QIODevice.WriteOnly)
        stream << pixmap.toImage()
        self.setData("application/x-collage-pixmap", ba)
        
    @property
    def pixmap(self) -> QPixmap:
        """Get the stored pixmap."""
        return self._pixmap
        
    @property
    def source_widget(self) -> 'CollageCell':
        """Get the source cell widget."""
        return self._source_widget


class CollageCell(QFrame):
    """A cell in the collage grid that can hold an image with caption."""
    
    image_dropped = Signal(int)  # Signal emitted when an image is dropped on this cell
    
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        """
        Initialize a collage cell.
        
        Args:
            cell_id: Unique identifier for this cell
            cell_size: Size of the cell (width and height)
            parent: Parent widget
        """
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap = None  # Image pixmap
        self.scaled_pixmap = None  # Cached scaled pixmap
        self.caption = ""  # Optional caption text
        self.formatting = CaptionFormatting()
        self.caption_rect = None  # Cache for caption rectangle
        self.caption_bg_rect = None  # Cache for caption background rectangle
        
        # Configure appearance
        self.setAcceptDrops(True)
        self.setFixedSize(cell_size, cell_size)
        self.setFrameShape(QFrame.Panel)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet("""
            CollageCell {
                background-color: white;
                border: 1px solid #CCCCCC;
            }
        """)
        
        logger.debug(f"Cell {self.cell_id} created (size {cell_size}x{cell_size})")
        
    def resizeCell(self, new_size: int):
        """Resize the cell while preserving content."""
        self.setFixedSize(new_size, new_size)
        self.scaled_pixmap = None  # Clear cached scaled pixmap
        self.update()
        
    def setImage(self, pixmap: QPixmap, caption: str = ""):
        """
        Set the image and optional caption for this cell.
        
        Args:
            pixmap: The image pixmap
            caption: Optional caption text (default: empty)
        """
        # Calculate a reasonable maximum size to prevent memory issues
        max_dimension = 2000  # pixels
        if pixmap.width() > max_dimension or pixmap.height() > max_dimension:
            pixmap = pixmap.scaled(
                max_dimension, max_dimension, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
        self.pixmap = pixmap
        self.scaled_pixmap = None  # Clear cached scaled pixmap
        self.caption = caption
        self.update()
        logger.debug(f"Cell {self.cell_id}: Image set with caption '{caption}'")
        
    def clearImage(self):
        """Remove the image and caption from this cell."""
        self.pixmap = None
        self.scaled_pixmap = None
        self.caption = ""
        self.update()
        logger.debug(f"Cell {self.cell_id}: Cleared image and caption")
        
    def getScaledPixmap(self) -> Optional[QPixmap]:
        """Get or create a properly scaled version of the pixmap."""
        if not self.pixmap:
            return None
        
        current_size = self.contentsRect().size()
        
        if not self.scaled_pixmap or self.scaled_pixmap.size() != current_size:
            # Cache the scaled pixmap for better performance
            rect = self.contentsRect()
            self.scaled_pixmap = self.pixmap.scaled(
                rect.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
        return self.scaled_pixmap
        
    def draw_caption(self, painter: QPainter, rect: QRect):
        """
        Draw the caption text with formatting.
        
        Args:
            painter: Active QPainter object
            rect: Rectangle area of the cell
        """
        if not self.caption:
            return
            
        # Apply caption formatting
        font = painter.font()
        font = self.formatting.apply_to_font(font)
        painter.setFont(font)
        
        # Use cached text rectangles if available, otherwise calculate them
        if not self.caption_rect or not self.caption_bg_rect:
            # Measure text size
            metrics = QFontMetrics(font)
            text_rect = metrics.boundingRect(rect, Qt.TextWordWrap, self.caption)
            
            # Position at bottom center with margins
            text_width = min(rect.width() - 10, text_rect.width())
            text_height = text_rect.height()
            self.caption_rect = QRect(
                rect.center().x() - text_width // 2,
                rect.bottom() - text_height - 5,
                text_width,
                text_height
            )
            
            # Calculate background rectangle
            self.caption_bg_rect = self.caption_rect.adjusted(-4, -2, 4, 2)
        
        # Draw semi-transparent background
        painter.fillRect(self.caption_bg_rect, QColor(0, 0, 0, 180))
        
        # Draw text
        painter.setPen(self.formatting.color)
        painter.drawText(self.caption_rect, Qt.AlignCenter | Qt.TextWordWrap, self.caption)
        
    def paintEvent(self, event):
        """Handle paint events for the cell."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        rect = self.contentsRect()
        
        if self.pixmap:
            # Use the cached scaled pixmap
            scaled = self.getScaledPixmap()
            
            # Center the pixmap in the cell
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            target = QRect(x, y, scaled.width(), scaled.height())
            
            # Draw image
            painter.drawPixmap(target, scaled, scaled.rect())
            
            # Draw caption if present
            if self.caption:
                self.draw_caption(painter, rect)
        else:
            # Draw placeholder
            painter.fillRect(rect, Qt.white)
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(rect, Qt.AlignCenter, "Drop Image Here")
            
    def mousePressEvent(self, event):
        """Handle mouse press events to initiate drag operations."""
        if event.button() == Qt.LeftButton and self.pixmap:
            logger.debug(f"Cell {self.cell_id}: Starting drag operation")
            
            # Create drag object
            drag = QDrag(self)
            mime_data = ImageMimeData(self.pixmap, self)
            drag.setMimeData(mime_data)
            
            # Create thumbnail for drag image
            thumb_size = min(128, self.width() // 2)
            thumb = self.pixmap.scaled(
                thumb_size, thumb_size, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            # Set the drag pixmap with offset to center under cursor
            drag.setPixmap(thumb)
            drag.setHotSpot(QPoint(thumb.width() // 2, thumb.height() // 2))
            
            # Execute drag operation
            result = drag.exec(Qt.MoveAction)
            logger.debug(f"Cell {self.cell_id}: Drag completed with result {result}")
            
    def mouseDoubleClickEvent(self, event):
        """Handle double-click events for caption editing."""
        if self.pixmap:
            current = self.caption
            new_caption, ok = QInputDialog.getText(
                self, 
                "Edit Caption", 
                "Caption for this image:", 
                text=current
            )
            
            if ok and new_caption != current:
                self.caption = new_caption
                self.update()
                logger.debug(f"Cell {self.cell_id}: Caption updated to '{new_caption}'")
                
    def dragEnterEvent(self, event):
        """Handle drag enter events to accept images."""
        mime = event.mimeData()
        
        # Accept drag if it contains images
        if mime.hasUrls() or mime.hasFormat("application/x-collage-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()
            
    def dragMoveEvent(self, event):
        """Handle drag move events more intelligently."""
        mime = event.mimeData()
        
        # Accept drag if it contains images
        if mime.hasUrls() or mime.hasFormat("application/x-collage-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()
            
    def dropEvent(self, event):
        """Handle drop events for image placement or swapping with animation."""
        logger.debug(f"Cell {self.cell_id}: Processing drop event")
        mime = event.mimeData()
        
        # Case 1: Internal drag from another cell
        if mime.hasFormat("application/x-collage-pixmap"):
            source_cell = mime.source_widget
            
            if source_cell and source_cell is not self:
                logger.debug(f"Cell {self.cell_id}: Swapping with Cell {source_cell.cell_id}")
                
                # Store current pixmaps for animation
                source_pixmap = source_cell.pixmap
                target_pixmap = self.pixmap
                
                # Swap all content between cells
                self.pixmap, source_cell.pixmap = source_cell.pixmap, self.pixmap
                self.caption, source_cell.caption = source_cell.caption, self.caption
                self.scaled_pixmap = None
                source_cell.scaled_pixmap = None
                
                # Clear cached caption rectangles
                self.caption_rect = None
                self.caption_bg_rect = None
                source_cell.caption_rect = None
                source_cell.caption_bg_rect = None
                
                # Update both cells
                self.update()
                source_cell.update()
                event.acceptProposedAction()
                return
                
        # Case 2: External file drop
        elif mime.hasUrls():
            url = mime.urls()[0]
            file_path = url.toLocalFile()
            
            if file_path and os.path.isfile(file_path):
                self._loadExternalImage(file_path)
                event.acceptProposedAction()
                return
                
        event.ignore()
        
    def _loadExternalImage(self, file_path: str):
        """
        Load an external image file asynchronously with format validation.
        
        Args:
            file_path: Path to the image file
        """
        # Validate file extension
        valid_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext not in valid_extensions:
            QMessageBox.warning(
                self,
                "Invalid File Format",
                f"The selected file is not a supported image format. Please select a file with one of these extensions: {', '.join(valid_extensions)}"
            )
            return
            
        # Validate file size to prevent crashes
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 10:  # Warn for files over 10MB
                response = QMessageBox.warning(
                    self,
                    "Large File Warning",
                    f"The selected image is {file_size_mb:.1f}MB and may cause performance issues. Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if response == QMessageBox.No:
                    return
        except Exception as e:
            logger.warning(f"Could not check file size: {str(e)}")
            
        # Start loading thread
        self.loader = ImageLoadWorker(file_path)
        self.loader.finished.connect(self._onImageLoaded)
        self.loader.error.connect(self._onImageLoadError)

        # Show progress dialog for larger files
        if file_size_mb > 5:
            self.progress = QProgressDialog("Loading image...", "Cancel", 0, 0, self)
            self.progress.setWindowModality(Qt.WindowModal)
            
            # Connect cancel button
            self.progress.canceled.connect(self._cancelImageLoading)
            self.progress.show()

        self.loader.start()
        
    def _cancelImageLoading(self):
        """Cancel the current image loading operation."""
        if hasattr(self, 'loader'):
            self.loader.cancel()
            self.loader.wait()
            self.loader.deleteLater()
            delattr(self, 'loader')
            
        if hasattr(self, 'progress'):
            self.progress.close()
            delattr(self, 'progress')

    def _onImageLoaded(self, pixmap: QPixmap, filename: str):
        """Callback when image loading is complete."""
        # Set a reasonable size limit for images to prevent memory issues
        max_size = 2000
        if pixmap.width() > max_size or pixmap.height() > max_size:
            pixmap = pixmap.scaled(
                max_size, max_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        
        self.setImage(pixmap, "")  # Empty caption by default
        
        # Close progress dialog if exists
        if hasattr(self, 'progress'):
            self.progress.close()
            delattr(self, 'progress')
            
        # Clean up the loader thread
        if hasattr(self, 'loader'):
            self.loader.deleteLater()
            delattr(self, 'loader')
            
        # Signal that image was dropped successfully
        self.image_dropped.emit(self.cell_id)
        
    def _onImageLoadError(self, error_message: str):
        """Callback when image loading fails."""
        if hasattr(self, 'progress'):
            self.progress.close()
            
        QMessageBox.critical(
            self,
            "Image Load Error",
            f"Failed to load image: {error_message}"
        )
        
        # Clean up the loader thread
        if hasattr(self, 'loader'):
            self.loader.deleteLater()


class CollageWidget(QWidget):
    """Widget to display a grid of CollageCell objects."""
    
    def __init__(self, rows=DEFAULT_ROWS, columns=DEFAULT_COLUMNS, 
                 cell_size=DEFAULT_CELL_SIZE, spacing=DEFAULT_SPACING, parent=None):
        """
        Initialize the collage widget.
        
        Args:
            rows: Number of rows in the grid
            columns: Number of columns in the grid
            cell_size: Size of each cell (width and height)
            spacing: Spacing between cells
            parent: Parent widget
        """
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.cell_size = cell_size
        self.spacing = spacing
        self.cells = []
        
        # Set appearance
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #333333;")
        
        # Setup layout
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(self.spacing)
        self.grid_layout.setContentsMargins(self.spacing, self.spacing, 
                                            self.spacing, self.spacing)
        self.setLayout(self.grid_layout)
        
        # Create cells
        self.populate_grid()
        self.setFixedSize(self.calculate_ideal_size())
        
        logger.debug(f"CollageWidget created with {rows}x{columns} grid")
        
    def calculate_ideal_size(self) -> QSize:
        """Calculate the ideal size for the widget based on content."""
        width = (self.columns * self.cell_size) + ((self.columns + 1) * self.spacing)
        height = (self.rows * self.cell_size) + ((self.rows + 1) * self.spacing)
        return QSize(width, height)
        
    def populate_grid(self):
        """Create and arrange cells in the grid layout."""
        # Remove existing cells first
        for cell in self.cells:
            self.grid_layout.removeWidget(cell)
            cell.deleteLater()
            
        self.cells = []
        
        # Create new cells
        cell_id = 1
        for row in range(self.rows):
            for col in range(self.columns):
                cell = CollageCell(cell_id, self.cell_size, self)
                self.grid_layout.addWidget(cell, row, col)
                self.cells.append(cell)
                cell_id += 1
                
        logger.debug(f"Grid populated with {len(self.cells)} cells")
        
    def update_grid(self, rows: int, columns: int, preserve_content: bool = True):
        """
        Update the grid dimensions, optionally preserving content.
        
        Args:
            rows: New number of rows
            columns: New number of columns
            preserve_content: Whether to preserve existing cell content
        """
        logger.debug(f"Updating grid to {rows}x{columns} (preserve_content={preserve_content})")
        
        if not preserve_content or (rows * columns) != len(self.cells):
            # Complete rebuild needed
            self.rows = rows
            self.columns = columns
            self.populate_grid()
        else:
            # Just reposition existing cells
            self.rows = rows
            self.columns = columns
            
            # Take all widgets from layout
            for i in range(len(self.cells)):
                self.grid_layout.removeWidget(self.cells[i])
                
            # Reposition them
            for index, cell in enumerate(self.cells):
                row = index // columns
                col = index % columns
                self.grid_layout.addWidget(cell, row, col)
                
        # Update the widget size
        self.setFixedSize(self.calculate_ideal_size())
        
    def resize_cells(self, new_size: int):
        """Resize all cells in the collage."""
        self.cell_size = new_size
        
        for cell in self.cells:
            cell.resizeCell(new_size)
            
        self.setFixedSize(self.calculate_ideal_size())
        
    def clear_all_cells(self):
        """Clear all images from cells."""
        for cell in self.cells:
            cell.clearImage()
            
    def save_to_image(self, file_path: str) -> bool:
        """
        Save the collage as an image file.
        
        Args:
            file_path: Path where to save the image
            
        Returns:
            bool: True if save was successful, False otherwise
        """
        try:
            # Validate file path
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                
            # Check if file is writable
            if os.path.exists(file_path):
                if not os.access(file_path, os.W_OK):
                    logger.error(f"No write permission for {file_path}")
                    return False
                    
            # Create pixmap of correct size
            pixmap = QPixmap(self.size())
            pixmap.fill(Qt.transparent)
            
            # Create painter
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # Render widget to pixmap
            self.render(painter)
            painter.end()
            
            # Save to file
            success = pixmap.save(file_path)
            if success:
                logger.info(f"Collage saved to {file_path}")
                return True
            else:
                logger.error(f"Failed to save collage to {file_path}")
                return False
                
        except PermissionError as e:
            logger.error(f"Permission error saving collage: {str(e)}")
            return False
        except OSError as e:
            logger.error(f"OS error saving collage: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error saving collage: {str(e)}\n{traceback.format_exc()}")
            return False
            
    def get_cells_data(self) -> List[Dict[str, Any]]:
        """
        Get serializable data for all cells.
        
        Returns:
            List of dictionaries with cell data
        """
        cells_data = []
        
        for cell in self.cells:
            if cell.pixmap:
                # Store image as base64 or save to temporary file
                # This is just a placeholder - we'd implement proper serialization
                cells_data.append({
                    'has_image': True,
                    'caption': cell.caption,
                    'formatting': cell.formatting.to_dict()
                })
            else:
                cells_data.append({
                    'has_image': False
                })
                
        return cells_data
        
    def apply_caption_formatting(self, formatting: CaptionFormatting):
        """Apply formatting to all cell captions."""
        for cell in self.cells:
            # Copy formatting properties
            cell.formatting.enabled = formatting.enabled
            cell.formatting.font_size = formatting.font_size
            cell.formatting.bold = formatting.bold
            cell.formatting.italic = formatting.italic
            cell.formatting.underline = formatting.underline
            cell.formatting.color = formatting.color
            cell.update()


class FormattingPanel(QWidget):
    """Panel for caption formatting controls with improved UI."""
    
    format_changed = Signal(CaptionFormatting)
    
    def __init__(self, parent=None):
        """Initialize the formatting panel."""
        super().__init__(parent)
        self.formatting = CaptionFormatting()
        self.setup_ui()
        
    def setup_ui(self):
        """Create the UI components with improved layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Caption enabled checkbox
        self.caption_enabled = QCheckBox("Enable Captions")
        self.caption_enabled.setChecked(self.formatting.enabled)
        self.caption_enabled.toggled.connect(self._on_format_changed)
        main_layout.addWidget(self.caption_enabled)
        
        # Format controls container
        format_container = QWidget()
        layout = QHBoxLayout(format_container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Caption label
        caption_label = QLabel("Caption Format:")
        layout.addWidget(caption_label)
        
        # Font size control
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 36)
        self.font_size_spin.setValue(self.formatting.font_size)
        self.font_size_spin.setPrefix("Size: ")
        self.font_size_spin.valueChanged.connect(self._on_format_changed)
        layout.addWidget(self.font_size_spin)
        
        # Style checkboxes
        self.bold_checkbox = QCheckBox("Bold")
        self.bold_checkbox.setChecked(self.formatting.bold)
        self.bold_checkbox.toggled.connect(self._on_format_changed)
        layout.addWidget(self.bold_checkbox)
        
        self.italic_checkbox = QCheckBox("Italic")
        self.italic_checkbox.setChecked(self.formatting.italic)
        self.italic_checkbox.toggled.connect(self._on_format_changed)
        layout.addWidget(self.italic_checkbox)
        
        self.underline_checkbox = QCheckBox("Underline")
        self.underline_checkbox.setChecked(self.formatting.underline)
        self.underline_checkbox.toggled.connect(self._on_format_changed)
        layout.addWidget(self.underline_checkbox)
        
        # Color button
        self.color_button = QPushButton("Color")
        self.color_button.clicked.connect(self._show_color_dialog)
        self._update_color_button()
        layout.addWidget(self.color_button)
        
        # Add stretch at the end
        layout.addStretch()
        
        main_layout.addWidget(format_container)
        
        # Update enabled state
        self._update_enabled_state()
        
    def _update_enabled_state(self):
        """Update the enabled state of controls based on caption enabled checkbox."""
        enabled = self.caption_enabled.isChecked()
        for widget in self.findChildren(QWidget):
            if widget != self.caption_enabled:
                widget.setEnabled(enabled)
        
    def _update_color_button(self):
        """Update the color button appearance to show the current color."""
        color = self.formatting.color
        style = f"""
            QPushButton {{
                background-color: {color.name()};
                color: {QColor(255-color.red(), 255-color.green(), 255-color.blue()).name()};
                padding: 5px;
            }}
        """
        self.color_button.setStyleSheet(style)
        
    def _show_color_dialog(self):
        """Show color picker dialog to select caption color."""
        color = QColorDialog.getColor(
            self.formatting.color, 
            self, 
            "Select Caption Color"
        )
        
        if color.isValid():
            self.formatting.color = color
            self._update_color_button()
            self._on_format_changed()
            
    def _on_format_changed(self):
        """Handle any format change and emit signal."""
        self.formatting.enabled = self.caption_enabled.isChecked()
        self.formatting.font_size = self.font_size_spin.value()
        self.formatting.bold = self.bold_checkbox.isChecked()
        self.formatting.italic = self.italic_checkbox.isChecked()
        self.formatting.underline = self.underline_checkbox.isChecked()
        
        # Update enabled state
        self._update_enabled_state()
        
        # Emit the updated formatting
        self.format_changed.emit(self.formatting)
        
    def get_current_formatting(self) -> CaptionFormatting:
        """Get the current formatting configuration."""
        return self.formatting


class MainWindow(QMainWindow):
    """Main application window for the Collage Maker."""
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(800, 600)

        # Set application icon
        self.setWindowIcon(QIcon.fromTheme("image-x-generic"))
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QVBoxLayout(central_widget)
        
        # Add control panels
        self.main_layout.addLayout(self.create_grid_controls())
        self.main_layout.addWidget(self.create_formatting_panel())
        
        # Create collage widget
        self.collage = CollageWidget(
            rows=self.rows_spin.value(), 
            columns=self.cols_spin.value(), 
            cell_size=self.cell_size_spin.value()
        )
        self.main_layout.addWidget(self.collage, alignment=Qt.AlignCenter)
        
        # Add status bar
        self.statusBar().showMessage("Ready")
        
        # Load settings
        self.load_settings()
        
        logger.info("Application initialized")
        
    def create_grid_controls(self) -> QHBoxLayout:
        """
        Create the grid control panel.
        
        Returns:
            Layout containing grid controls
        """
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(10, 10, 10, 10)
        
        # Grid size controls
        grid_controls = QHBoxLayout()
        grid_controls.setSpacing(10)
        
        # Rows control
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setMaximum(10)
        self.rows_spin.setValue(DEFAULT_ROWS)
        self.rows_spin.setPrefix("Rows: ")
        
        # Columns control
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1)
        self.cols_spin.setMaximum(10)
        self.cols_spin.setValue(DEFAULT_COLUMNS)
        self.cols_spin.setPrefix("Columns: ")
        
        # Cell size control
        self.cell_size_spin = QSpinBox()
        self.cell_size_spin.setMinimum(MIN_CELL_SIZE)
        self.cell_size_spin.setMaximum(MAX_CELL_SIZE)
        self.cell_size_spin.setSingleStep(10)
        self.cell_size_spin.setValue(DEFAULT_CELL_SIZE)
        self.cell_size_spin.setPrefix("Cell Size: ")
        
        # Update button
        update_button = QPushButton("Update Grid")
        update_button.clicked.connect(self.update_collage)
        
        # Add grid controls to layout
        grid_controls.addWidget(self.rows_spin)
        grid_controls.addWidget(self.cols_spin)
        grid_controls.addWidget(self.cell_size_spin)
        grid_controls.addWidget(update_button)
        
        # File operations
        file_controls = QHBoxLayout()
        file_controls.setSpacing(10)
        
        # Clear button
        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self.clear_collage)
        
        # Save button
        save_button = QPushButton("Save Collage")
        save_button.clicked.connect(self.save_collage)
        
        # Add file controls to layout
        file_controls.addWidget(clear_button)
        file_controls.addWidget(save_button)

        # Add both control groups to main controls layout
        controls_layout.addLayout(grid_controls)
        controls_layout.addStretch()
        controls_layout.addLayout(file_controls)
        
        return controls_layout
        
    def create_formatting_panel(self) -> FormattingPanel:
        """
        Create the caption formatting panel.
        
        Returns:
            The formatting panel widget
        """
        panel = FormattingPanel()
        panel.format_changed.connect(self.update_caption_format)
        return panel
        
    def update_caption_format(self, formatting: CaptionFormatting):
        """
        Update the caption formatting for all cells.
        
        Args:
            formatting: The formatting to apply
        """
        self.collage.apply_caption_formatting(formatting)
        
    def update_collage(self):
        """Update the collage grid with current settings."""
        rows = self.rows_spin.value()
        columns = self.cols_spin.value()
        cell_size = self.cell_size_spin.value()
        
        # Check if only the cell size changed
        if rows == self.collage.rows and columns == self.collage.columns:
            if cell_size != self.collage.cell_size:
                self.collage.resize_cells(cell_size)
        else:
            # Grid dimensions changed
            self.collage.update_grid(rows, columns)
            
            # If cell size also changed, update that too
            if cell_size != self.collage.cell_size:
                self.collage.resize_cells(cell_size)
                
        # Update status
        self.statusBar().showMessage(f"Grid updated to {rows}x{columns}, cell size: {cell_size}px")
        
    def clear_collage(self):
        """Clear all images from the collage."""
        response = QMessageBox.question(
            self,
            "Clear Confirmation",
            "Are you sure you want to clear all images?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if response == QMessageBox.Yes:
            self.collage.clear_all_cells()
            self.statusBar().showMessage("All images cleared")
        
    def save_collage(self):
        """Save the collage as an image file with improved error handling."""
        # Check if there are any images to save
        has_images = any(cell.pixmap is not None for cell in self.collage.cells)
        if not has_images:
            QMessageBox.warning(
                self,
                "No Images",
                "There are no images in the collage to save. Please add some images first."
            )
            return
        
        # Show save dialog
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Collage",
            QDir.homePath() + "/collage.png",  # Default name and location
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)"
        )
        
        if not file_path:
            return
            
        # Add extension if missing
        if not (file_path.lower().endswith(".png") or 
                file_path.lower().endswith(".jpg") or 
                file_path.lower().endswith(".jpeg")):
            if "PNG" in selected_filter:
                file_path += ".png"
            else:
                file_path += ".jpg"
                
        # Save the collage
        try:
            # Check if file exists and confirm overwrite
            if os.path.exists(file_path):
                response = QMessageBox.question(
                    self,
                    "File Exists",
                    f"The file {os.path.basename(file_path)} already exists. Do you want to overwrite it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if response == QMessageBox.No:
                    return
            
            # Create progress dialog for saving
            progress = QProgressDialog("Saving collage...", "Cancel", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setCancelButton(None)  # Disable cancel to prevent partial saves
            progress.show()
            
            # Save in a separate thread to prevent UI freezing
            QApplication.processEvents()
            
            if self.collage.save_to_image(file_path):
                self.statusBar().showMessage(f"Collage saved to {file_path}")
            else:
                QMessageBox.critical(
                    self,
                    "Save Error",
                    "Failed to save the collage. Please check if you have write permissions for this location."
                )
            
            progress.close()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"An error occurred while saving: {str(e)}"
            )
            
    def save_settings(self):
        """Save application settings."""
        settings = QSettings("CollageMaker", "Preferences")
        
        # Save window state
        settings.setValue("window/geometry", self.saveGeometry())
        
        # Save grid settings
        settings.setValue("grid/rows", self.rows_spin.value())
        settings.setValue("grid/columns", self.cols_spin.value())
        settings.setValue("grid/cell_size", self.cell_size_spin.value())
        
        # Save caption formatting
        panel = self.findChild(FormattingPanel)
        if panel:
            fmt = panel.get_current_formatting()
            settings.setValue("caption/font_size", fmt.font_size)
            settings.setValue("caption/bold", fmt.bold)
            settings.setValue("caption/italic", fmt.italic)
            settings.setValue("caption/underline", fmt.underline)
            settings.setValue("caption/color", fmt.color.name())
            
    def load_settings(self):
        """Load application settings."""
        settings = QSettings("CollageMaker", "Preferences")
        
        # Load window state
        geometry = settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
            
        # Load grid settings
        rows = settings.value("grid/rows", DEFAULT_ROWS, type=int)
        columns = settings.value("grid/columns", DEFAULT_COLUMNS, type=int)
        cell_size = settings.value("grid/cell_size", DEFAULT_CELL_SIZE, type=int)
        
        self.rows_spin.setValue(rows)
        self.cols_spin.setValue(columns)
        self.cell_size_spin.setValue(cell_size)
        
        # Load caption formatting
        panel = self.findChild(FormattingPanel)
        if panel:
            fmt = panel.formatting
            fmt.font_size = settings.value("caption/font_size", DEFAULT_CAPTION_SIZE, type=int)
            fmt.bold = settings.value("caption/bold", True, type=bool)
            fmt.italic = settings.value("caption/italic", True, type=bool)
            fmt.underline = settings.value("caption/underline", True, type=bool)
            
            color_str = settings.value("caption/color", "#FFFF00")
            fmt.color = QColor(color_str)
            
            # Update UI to reflect loaded settings
            panel.font_size_spin.setValue(fmt.font_size)
            panel.bold_checkbox.setChecked(fmt.bold)
            panel.italic_checkbox.setChecked(fmt.italic)
            panel.underline_checkbox.setChecked(fmt.underline)
            panel._update_color_button()
            
            # Apply formatting to cells
            self.update_caption_format(fmt)
            
        # Update collage with loaded settings
        self.update_collage()
        
    def closeEvent(self, event):
        """Handle window close event to save settings."""
        self.save_settings()
        super().closeEvent(event)


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        
        # Set application style
        app.setStyle("Fusion")
        
        # Create and show the main window
        window = MainWindow()
        window.show()
        
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"Unhandled exception: {str(e)}\n{traceback.format_exc()}")
        QMessageBox.critical(
            None,
            "Critical Error",
            f"The application encountered a critical error and needs to close.\n\n{str(e)}"
        )
        sys.exit(1)
