import logging
from typing import Optional
from PySide6.QtWidgets import QLabel, QMenu, QAction
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QPainter, QColor
from utils.image_processor import ImageProcessor

class ImageLabel(QLabel):
    """A custom QLabel for handling image display and drag-drop."""
    
    imageDropped = Signal()

    def __init__(self):
        """Initialize the ImageLabel widget."""
        super().__init__()
        self.original_pixmap: Optional[QPixmap] = None
        
        # Set up UI properties
        self.setAlignment(Qt.AlignCenter)
        self.setText("Drag an image here")
        
        # Set up drag and drop
        self.setAcceptDrops(True)
        
        # Set up context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, position) -> None:
        """Show the context menu at the given position."""
        if not self.original_pixmap:
            return
            
        menu = QMenu(self)
        clear_action = QAction("Clear Image", self)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)
        menu.exec(self.mapToGlobal(position))

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle drop events for images."""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if ImageProcessor.is_valid_image(file_path):
                self.setImage(file_path)
                break
        event.acceptProposedAction()

    def setImage(self, file_path: str):
        """
        Set the image from the given file path.
        
        Args:
            file_path (str): Path to the image file.
        """
        try:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                self.original_pixmap = pixmap
                self._update_pixmap()
                self.setProperty('hasImage', True)
                self.style().unpolish(self); self.style().polish(self)
                self.imageDropped.emit()
            else:
                raise ValueError("Invalid image file")
        except Exception as e:
            logging.error(f"Error loading image {file_path}: {str(e)}")
            self.setText("Error loading image")

    def setPixmap(self, pixmap: QPixmap):
        """
        Set the pixmap and scale it to fit the label.
        
        Args:
            pixmap (QPixmap): The pixmap to set.
        """
        self.original_pixmap = pixmap
        self._update_pixmap()
        self.setProperty('hasImage', True)
        self.style().unpolish(self); self.style().polish(self)

    def _update_pixmap(self):
        """Update the displayed pixmap, scaling it to fit the label while maintaining aspect ratio."""
        if self.original_pixmap:
            scaled_pixmap = self.original_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            super().setPixmap(scaled_pixmap)
            self._center_pixmap()

    def _center_pixmap(self):
        """Center the pixmap in the label."""
        if self.pixmap():
            pixmap = self.pixmap()
            empty_space = self.size() - pixmap.size()
            self.setContentsMargins(
                empty_space.width() // 2,
                empty_space.height() // 2,
                empty_space.width() // 2,
                empty_space.height() // 2
            )

    def resizeEvent(self, event):
        """Handle resize events for the label."""
        super().resizeEvent(event)
        self._update_pixmap()

    def clear(self):
        """Clear the current image and reset the label text."""
        super().clear()
        self.original_pixmap = None
        self.setText("Drag an image here")
        self.setContentsMargins(0, 0, 0, 0)
        self.setProperty('hasImage', False)
        self.style().unpolish(self); self.style().polish(self)

    def paintEvent(self, event):
        """Custom paint event to draw the image and placeholder text."""
        super().paintEvent(event)
        if not self.original_pixmap and not self.text():
            painter = QPainter(self)
            painter.setPen(QColor('#888888'))
            painter.drawText(self.rect(), Qt.AlignCenter, "Drag an image here")

    def sizeHint(self) -> QSize:
        """Provide a size hint for the label."""
        return QSize(100, 100)  # Default size hint, adjust as needed
