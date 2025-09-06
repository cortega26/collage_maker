import logging
from typing import List, Optional, Dict
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QMessageBox,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QColor, QImage
from utils.collage_layouts import CollageLayouts
from utils.image_processor import ImageProcessor
from .image_label import ImageLabel

class CollageCanvas(QWidget):
    """
    A widget that displays and manages a collage of images.
    
    Signals:
        collageUpdated: Emitted when the collage content changes
        layoutChanged: Emitted when the layout changes
    """
    
    collageUpdated = pyqtSignal()
    layoutChanged = pyqtSignal(str)  # New signal for layout changes
    
    # Class constants
    SPACING = 2  # Spacing between images in pixels
    MAX_IMAGE_SIZE = 10000  # Maximum allowed image dimension
    MIN_IMAGE_SIZE = 50  # Minimum allowed image dimension
    AUTO_SAVE_INTERVAL = 300000  # 5 minutes in milliseconds

    def __init__(self):
        """Initialize the CollageCanvas widget."""
        super().__init__()
        self._init_ui()
        self._setup_auto_save()
        
    def _init_ui(self) -> None:
        """Initialize the UI components."""
        # Create grid layout for images
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(self.SPACING)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setAlignment(Qt.AlignCenter)
        
        # Configure widget properties
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(QSize(400, 300))
        
        self.image_labels: List[ImageLabel] = []
        self.current_layout = None
        self.setAcceptDrops(True)
        self._setup_layout("2x2")  # Default layout
        
    def _setup_auto_save(self) -> None:
        """Set up auto-save functionality."""
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self._auto_save)
        self.auto_save_timer.start(self.AUTO_SAVE_INTERVAL)
        self.temp_save_path = "temp/autosave_collage.tmp"
        
    def _auto_save(self) -> None:
        """Automatically save the current state to a temporary file."""
        if self.canSave():
            try:
                self._create_collage().save(self.temp_save_path)
                logging.info("Auto-saved collage state")
            except Exception as e:
                logging.error(f"Auto-save failed: {e}")

    def setLayout(self, layout_name: str) -> None:
        """
        Set the collage layout based on the given layout name.
        
        Args:
            layout_name (str): Name of the layout to set.
            
        Raises:
            ValueError: If the layout name is invalid
        """
        if not isinstance(layout_name, str):
            raise ValueError("Layout name must be a string")
            
        try:
            current_images = self._store_current_images()
            self._clear_layout()
            self._setup_layout(layout_name)
            self._restore_images(current_images)
            self.layoutChanged.emit(layout_name)
            self.collageUpdated.emit()
        except Exception as e:
            logging.error(f"Error setting layout '{layout_name}': {e}")
            self._handle_error("Layout Error", f"Failed to set layout: {e}")

    def _store_current_images(self) -> List[Optional[QPixmap]]:
        """
        Store and return the current images in the collage.
        
        Returns:
            List[Optional[QPixmap]]: List of current images
        """
        return [label.original_pixmap for label in self.image_labels]

    def _clear_layout(self) -> None:
        """Clear the existing layout and image labels safely."""
        try:
            for i in reversed(range(self.grid_layout.count())): 
                widget = self.grid_layout.itemAt(i).widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()  # Ensure proper cleanup
            self.image_labels.clear()
        except Exception as e:
            logging.error(f"Error clearing layout: {e}")
            raise

    def _setup_layout(self, layout_name: str) -> None:
        """
        Create a new layout based on the given layout name.
        
        Args:
            layout_name (str): Name of the layout to create.
            
        Raises:
            ValueError: If layout creation fails
        """
        try:
            self.current_layout = CollageLayouts.get_layout(layout_name)
            self._create_image_labels()
        except Exception as e:
            logging.error(f"Error setting up layout: {e}")
            raise ValueError(f"Failed to setup layout: {e}")

    def _create_image_labels(self) -> None:
        """Create and set up image labels for the current layout."""
        # Calculate dimensions
        canvas_size = self.size()
        cell_dimensions = self._calculate_cell_dimensions(canvas_size)
        
        # Create and add labels
        for dimensions in cell_dimensions:
            x = int(dimensions['x'])
            y = int(dimensions['y'])
            w = int(dimensions['width'])
            h = int(dimensions['height'])
            
            # Create and configure label
            label = self._create_image_label(QSize(w, h))
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.grid_layout.addWidget(label, y, x)
            self.image_labels.append(label)
            
        # Configure grid layout
        self.grid_layout.setSpacing(self.SPACING)
        self.grid_layout.setAlignment(Qt.AlignCenter)

    def _calculate_cell_dimensions(self, canvas_size: QSize) -> List[Dict[str, int]]:
        """
        Calculate the dimensions of each cell in the layout.
        
        Args:
            canvas_size (QSize): Size of the canvas
            
        Returns:
            List[Dict[str, int]]: List of cell dimensions
        """
        if not self.current_layout:
            raise ValueError("No layout set")
            
        width = max(self.MIN_IMAGE_SIZE, min(canvas_size.width(), self.MAX_IMAGE_SIZE))
        height = max(self.MIN_IMAGE_SIZE, min(canvas_size.height(), self.MAX_IMAGE_SIZE))
        
        return self.current_layout.get_cell_dimensions(width, height, self.SPACING)

    def _create_image_label(self, size: QSize) -> ImageLabel:
        """
        Create and configure an ImageLabel instance.
        
        Args:
            size (QSize): Size for the new label
            
        Returns:
            ImageLabel: Configured image label
        """
        label = ImageLabel()
        label.setMinimumSize(size)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        label.imageDropped.connect(self.onImageDropped)
        return label

    def _restore_images(self, images: List[Optional[QPixmap]]) -> None:
        """
        Restore the given images to the new layout.
        
        Args:
            images (List[Optional[QPixmap]]): List of pixmaps to restore
        """
        for i, pixmap in enumerate(images):
            if i < len(self.image_labels) and pixmap is not None:
                try:
                    self._validate_image_size(pixmap)
                    self.image_labels[i].setPixmap(pixmap)
                except ValueError as e:
                    logging.warning(f"Skipped restoring image {i}: {e}")

    def _validate_image_size(self, pixmap: QPixmap) -> None:
        """
        Validate image dimensions.
        
        Args:
            pixmap (QPixmap): Image to validate
            
        Raises:
            ValueError: If image dimensions are invalid
        """
        if pixmap.width() > self.MAX_IMAGE_SIZE or pixmap.height() > self.MAX_IMAGE_SIZE:
            raise ValueError("Image dimensions exceed maximum allowed size")
        if pixmap.width() < self.MIN_IMAGE_SIZE or pixmap.height() < self.MIN_IMAGE_SIZE:
            raise ValueError("Image dimensions below minimum allowed size")

    def _handle_error(self, title: str, message: str) -> None:
        """
        Display an error message to the user.
        
        Args:
            title (str): Error dialog title
            message (str): Error message
        """
        QMessageBox.warning(self, title, message)

    def saveCollage(self, file_path: str) -> bool:
        """
        Save the current collage to the specified file path.
        
        Args:
            file_path (str): Path to save the collage
            
        Returns:
            bool: True if save was successful
        """
        if not self._validate_collage():
            return False

        try:
            collage = self._create_collage()
            success = collage.save(file_path, quality=95)
            self._handle_save_result(success, file_path)
            return success
        except Exception as e:
            logging.error(f"Error saving collage: {e}")
            self._handle_error("Save Error", f"Failed to save collage: {e}")
            return False

    def _validate_collage(self) -> bool:
        """
        Validate that all cells in the collage contain images.
        
        Returns:
            bool: True if the collage is valid
        """
        if not all(label.original_pixmap for label in self.image_labels):
            QMessageBox.warning(self, "Incomplete Collage", 
                              "Please add images to all cells before saving.")
            return False
        return True

    def _create_collage(self) -> QImage:
        """
        Create and return a QImage of the current collage.
        
        Returns:
            QImage: The created collage
            
        Raises:
            ValueError: If collage creation fails
        """
        canvas_size = self.size()
        collage = QImage(canvas_size, QImage.Format_ARGB32)
        collage.fill(QColor('white'))
        
        painter = QPainter(collage)
        try:
            self._draw_collage(painter, canvas_size)
        finally:
            painter.end()
        
        return collage

    def _draw_collage(self, painter: QPainter, canvas_size: QSize) -> None:
        """
        Draw the collage using the given painter.
        
        Args:
            painter (QPainter): Painter to use
            canvas_size (QSize): Size of the canvas
        """
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        dimensions = self._calculate_layout_dimensions(canvas_size)
        for label, dim in zip(self.image_labels, dimensions):
            if label.original_pixmap:
                self._draw_image(
                    painter,
                    label.original_pixmap,
                    dim['x'],
                    dim['y'],
                    dim['width'],
                    dim['height']
                )

    def _calculate_layout_dimensions(self, canvas_size: QSize) -> List[Dict[str, int]]:
        """
        Calculate the dimensions for the current layout.
        
        Args:
            canvas_size (QSize): Size of the canvas
            
        Returns:
            List[Dict[str, int]]: Layout dimensions
        """
        width = max(self.MIN_IMAGE_SIZE, min(canvas_size.width(), self.MAX_IMAGE_SIZE))
        height = max(self.MIN_IMAGE_SIZE, min(canvas_size.height(), self.MAX_IMAGE_SIZE))
        
        return self.current_layout.get_cell_dimensions(width, height, self.SPACING)

    def _draw_image(self, painter: QPainter, pixmap: QPixmap, x: int, y: int, w: int, h: int) -> None:
        """
        Draw an image on the collage.
        
        Args:
            painter (QPainter): Painter to use
            pixmap (QPixmap): Image to draw
            x (int): X coordinate
            y (int): Y coordinate
            w (int): Width
            h (int): Height
        """
        scaled_pixmap = pixmap.scaled(
            QSize(w, h),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        x_offset = (w - scaled_pixmap.width()) // 2
        y_offset = (h - scaled_pixmap.height()) // 2
        painter.drawPixmap(x + x_offset, y + y_offset, scaled_pixmap)

    def _handle_save_result(self, success: bool, file_path: str) -> None:
        """
        Handle the result of the save operation.
        
        Args:
            success (bool): Whether the save operation was successful
            file_path (str): Path where the collage was saved
        """
        if success:
            QMessageBox.information(self, "Save Successful", 
                                  f"The collage has been saved successfully at:\n{file_path}")
        else:
            QMessageBox.warning(self, "Save Error", 
                              "Unable to save the collage. Please try a different location.")

    def onImageDropped(self) -> None:
        """Handle image drop events."""
        self.collageUpdated.emit()

    def setSpacing(self, spacing: int) -> None:
        """
        Set the spacing between images.
        
        Args:
            spacing (int): New spacing value in pixels
        """
        if spacing < 0:
            raise ValueError("Spacing must be non-negative")
            
        self.SPACING = spacing
        self.grid_layout.setSpacing(spacing)
        self.update()
        self.collageUpdated.emit()

    def getImages(self) -> List[QPixmap]:
        """
        Return a list of pixmaps for all non-empty image labels.
        
        Returns:
            List[QPixmap]: List of images
        """
        return [label.original_pixmap for label in self.image_labels if label.original_pixmap]

    def clearImages(self) -> None:
        """Clear all images from the collage."""
        for label in self.image_labels:
            label.clear()
        self.collageUpdated.emit()

    def canSave(self) -> bool:
        """
        Check if the collage is ready to be saved.
        
        Returns:
            bool: True if all cells contain images
        """
        return all(label.original_pixmap for label in self.image_labels)

    def dragEnterEvent(self, event) -> None:
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        """Handle drop events for images."""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if ImageProcessor.is_valid_image(file_path):
                empty_label = next((label for label in self.image_labels 
                                  if not label.original_pixmap), None)
                if empty_label:
                    empty_label.setImage(file_path)
        self.collageUpdated.emit()

    def resizeEvent(self, event) -> None:
        """Handle resize events for the collage canvas."""
        super().resizeEvent(event)
        if self.current_layout:
            self.setLayout(self.current_layout.name)
