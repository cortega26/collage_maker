"""
Collage Maker - A PySide6 application to create and manage image collages.
Improvements include drag/drop reordering, saving collages, and responsive grid updates.
"""

import sys
import logging
import traceback

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QSpinBox,
    QHBoxLayout, QPushButton, QFileDialog, QSizePolicy
)
from PySide6.QtCore import Qt, QMimeData, QByteArray, QDataStream, QIODevice, QRect, QSize
from PySide6.QtGui import QDrag, QPixmap, QPainter, QImageReader

# Configuración básica de logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

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
# Widget de cada celda del collage (cuadrada)
# ========================================================

class CollageCell(QWidget):
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap = None  # Imagen cargada
        self.setAcceptDrops(True)
        # Fijamos el tamaño de la celda
        self.setFixedSize(cell_size, cell_size)
        self.setStyleSheet("background-color: transparent;")
        logging.info("Celda %d creada (tamaño %dx%d).", self.cell_id, cell_size, cell_size)

    def setImage(self, pixmap: QPixmap):
        self.pixmap = pixmap
        self.update()
        logging.info("Celda %d: imagen cargada.", self.cell_id)

    def clearImage(self):
        self.pixmap = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()  # rectángulo completo de la celda (cuadrado)
        if self.pixmap:
            # Escalar la imagen manteniendo su proporción
            scaled = self.pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            # Calcular coordenadas para centrar la imagen en el cuadrado
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            target = QRect(x, y, scaled.width(), scaled.height())
            painter.drawPixmap(target, scaled, scaled.rect())
        else:
            painter.fillRect(rect, Qt.white)
            painter.setPen(Qt.gray)
            painter.drawText(rect, Qt.AlignCenter, "Drop Image Here")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.pixmap:
            logging.info("Celda %d: iniciando drag.", self.cell_id)
            drag = QDrag(self)
            mime_data = ImageMimeData(self.pixmap, self)
            drag.setMimeData(mime_data)
            drag.setPixmap(self.pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            result = drag.exec(Qt.MoveAction)
            logging.info("Celda %d: drag finalizado (resultado: %s).", self.cell_id, result)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        logging.info("Celda %d: dropEvent.", self.cell_id)
        mime = event.mimeData()
        if mime.hasFormat("application/x-pixmap"):
            source_cell = getattr(mime, "source_widget", None)
            if source_cell and source_cell is not self:
                logging.info("Celda %d: intercambiando imagen con Celda %d.", self.cell_id, source_cell.cell_id)
                self.pixmap, source_cell.pixmap = source_cell.pixmap, self.pixmap
                self.update()
                source_cell.update()
                event.acceptProposedAction()
                return
        elif mime.hasUrls():
            file_path = mime.urls()[0].toLocalFile()
            if file_path:
                try:
                    logging.info("Celda %d: cargando imagen desde %s", self.cell_id, file_path)
                    reader = QImageReader(file_path)
                    image = reader.read()
                    if image.isNull():
                        raise ValueError("Imagen inválida o con formato no soportado.")
                    self.setImage(QPixmap.fromImage(image))
                    event.acceptProposedAction()
                except Exception as e:
                    logging.error("Celda %d: Error al cargar la imagen: %s", self.cell_id, e)
                    event.ignore()
                return
        event.ignore()

# ========================================================
# Widget del Collage
# ========================================================

class CollageWidget(QWidget):
    """
    Widget for displaying a grid of CollageCell(s).
    
    Parameters:
        rows (int): Number of rows in the grid.
        columns (int): Number of columns in the grid.
        cell_size (int): The fixed pixel size for each cell.
    """
    def __init__(self, rows=2, columns=2, cell_size=260, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.cell_size = cell_size
        self.spacing = 2
        self.setup_layout()
        self.setStyleSheet("background-color: black;")
        self.cells = []
        self.populate_grid()
        # Fijar el tamaño ideal del widget collage
        self.setFixedSize(self.idealSize())

    def setup_layout(self):
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(self.spacing)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.grid_layout)

    def idealSize(self):
        """
        Calculate the ideal widget size based on cell dimensions and spacing.
        
        Returns:
            QSize: The ideal size for the collage widget.
        """
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

    def update_grid(self, rows, columns):
        # Case 1: Rearrangement: total cell count is unchanged
        if rows * columns == len(self.cells):
            # Remove all widgets from the grid layout.
            while self.grid_layout.count():
                self.grid_layout.takeAt(0)
            # Re-add the existing cells in the new order.
            for index, cell in enumerate(self.cells):
                i, j = divmod(index, columns)
                self.grid_layout.addWidget(cell, i, j)
        else:
            # Case 2: Full repopulation: the total number of cells has changed.
            self.rows = rows
            self.columns = columns
            self.populate_grid()

        # Update dimensions and reassign rows/columns.
        self.rows = rows
        self.columns = columns
        logging.info("Collage: actualizando a %d filas x %d columnas.", rows, columns)
        self.setFixedSize(self.idealSize())

    def sizeHint(self):
        return self.idealSize()

# ========================================================
# Ventana Principal
# ========================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker - PySide6")
        self.resize(800, 600)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.addLayout(self.create_controls_panel())
        self.collage = CollageWidget(rows=self.rows_spin.value(), columns=self.cols_spin.value(), cell_size=260)
        main_layout.addWidget(self.collage, alignment=Qt.AlignCenter)
        logging.info("Ventana principal inicializada.")

    def create_controls_panel(self):
        controls_layout = QHBoxLayout()
        # SpinBox for rows
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setValue(2)
        self.rows_spin.setPrefix("Filas: ")
        # SpinBox for columns
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1)
        self.cols_spin.setValue(2)
        self.cols_spin.setPrefix("Columnas: ")
        # Update and Save buttons
        update_button = QPushButton("Actualizar Collage")
        update_button.clicked.connect(self.update_collage)
        save_button = QPushButton("Guardar Collage")
        save_button.clicked.connect(self.save_collage)
        # Add to layout
        controls_layout.addWidget(self.rows_spin)
        controls_layout.addWidget(self.cols_spin)
        controls_layout.addWidget(update_button)
        controls_layout.addWidget(save_button)
        return controls_layout

    def update_collage(self):
        rows = self.rows_spin.value()
        columns = self.cols_spin.value()
        logging.info("Actualizando collage: %d filas x %d columnas.", rows, columns)
        self.collage.update_grid(rows, columns)

    def save_collage(self):
        logging.info("Guardando collage...")
        try:
            pixmap = self.collage.grab()

            file_path, selected_filter = QFileDialog.getSaveFileName(
                self, 
                "Guardar Collage",
                "", 
                "PNG Files (*.png);;JPEG Files (*.jpg)"
            )

            if not file_path:
                logging.info("Guardado cancelado por el usuario.")
                return

            # Optional: Validate file extension
            if not (file_path.lower().endswith(".png") or file_path.lower().endswith(".jpg") or file_path.lower().endswith(".jpeg")):
                raise ValueError("El archivo debe tener extensión .png, .jpg o .jpeg.")

            if pixmap.save(file_path):
                logging.info("Collage guardado en %s", file_path)
            else:
                raise IOError("No se pudo guardar la imagen en el archivo especificado.")

        except Exception as e:
            logging.error("Se produjo un error al guardar el collage: %s\n%s", e, traceback.format_exc())

# ========================================================
# Punto de Entrada
# ========================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
