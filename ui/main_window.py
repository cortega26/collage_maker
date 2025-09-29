import logging
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QFileDialog, QMessageBox
)
from .collage_canvas import CollageCanvas
from utils.collage_layouts import CollageLayouts

class MainWindow(QMainWindow):
    """Main window of the application."""
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Collage Creator")
        self.setMinimumSize(800, 600)
        
        # Create central widget and main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Initialize components
        self.collage_canvas: Optional[CollageCanvas] = None
        self._init_ui()
        
    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self._setup_controls()
        self._setup_collage_canvas()
        
    def _setup_controls(self) -> None:
        """Set up the control buttons and layout selector."""
        controls_layout = QHBoxLayout()
        
        # Layout selector
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(CollageLayouts.get_layout_names())
        self.layout_combo.currentTextChanged.connect(self._change_layout)
        self.layout_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px 10px;
                min-width: 6em;
            }
            QComboBox::drop-down {
                border-left: 1px solid #ccc;
                width: 20px;
            }
            QComboBox::down-arrow {
                width: 12px;
                height: 12px;
            }
        """)
        controls_layout.addWidget(self.layout_combo)
        
        # Clear button
        self.clear_button = QPushButton("Clear Collage")
        self.clear_button.clicked.connect(self._clear_collage)
        controls_layout.addWidget(self.clear_button)
        
        # Save button
        self.save_button = QPushButton("Save Collage")
        self.save_button.clicked.connect(self._save_collage)
        self.save_button.setEnabled(False)
        controls_layout.addWidget(self.save_button)
        
        # Add controls to main layout
        self.main_layout.addLayout(controls_layout)
        
    def _setup_collage_canvas(self) -> None:
        """Set up the collage canvas."""
        try:
            self.collage_canvas = CollageCanvas()
            self.collage_canvas.collageUpdated.connect(self._update_save_button)
            self.main_layout.addWidget(self.collage_canvas)
        except Exception as e:
            logging.error(f"Error setting up collage canvas: {e}")
            QMessageBox.critical(self, "Error", f"Failed to initialize collage canvas: {e}")
        
    def _change_layout(self, layout_name: str) -> None:
        """
        Change the collage layout.
        
        Args:
            layout_name (str): Name of the new layout
        """
        try:
            self.collage_canvas.setLayout(layout_name)
        except Exception as e:
            logging.error(f"Error changing layout: {e}")
            QMessageBox.warning(self, "Error", f"Could not change the layout: {e}")
        
    def _clear_collage(self) -> None:
        """Clear the current collage after confirmation."""
        reply = QMessageBox.question(
            self, 
            'Confirm Clear', 
            "Are you sure you want to clear the collage?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.collage_canvas.clearImages()
            except Exception as e:
                logging.error(f"Error clearing collage: {e}")
                QMessageBox.warning(self, "Error", f"Could not clear the collage: {e}")
        
    def _save_collage(self) -> None:
        """Save the current collage."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Collage",
            "",
            "JPEG (*.jpg);;PNG (*.png);;WEBP (*.webp)"
        )
        
        if file_path:
            try:
                success = self.collage_canvas.saveCollage(file_path)
                if not success:
                    raise Exception("Failed to save the collage")
            except Exception as e:
                logging.error(f"Error saving collage: {e}")
                QMessageBox.warning(self, "Error", f"Could not save the collage: {e}")
        
    def _update_save_button(self) -> None:
        """Update the state of the save button."""
        self.save_button.setEnabled(self.collage_canvas.canSave())

    def closeEvent(self, event) -> None:
        """
        Handle the window close event.
        
        Args:
            event: The close event
        """
        if self.collage_canvas and self.collage_canvas.canSave():
            reply = QMessageBox.question(
                self,
                'Confirm Exit',
                "You have an unsaved collage. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
