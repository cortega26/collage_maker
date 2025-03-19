import sys
import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel,
    QSpinBox, QHBoxLayout, QPushButton, QFrame, QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, QMimeData, QByteArray, QDataStream, QIODevice
from PySide6.QtGui import QDrag, QPixmap, QImageReader

# Configuración de logging (nivel INFO para producción; cambiar a DEBUG para depuración detallada)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# =======================
# Clases de soporte
# =======================

class ImageMimeData(QMimeData):
    """
    Subclase de QMimeData para almacenar un QPixmap y la referencia al widget de origen.
    Esto permite intercambiar imágenes entre celdas sin perder la referencia.
    """
    def __init__(self, pixmap: QPixmap, source_widget: "CollageCell"):
        super().__init__()
        self._pixmap = pixmap
        self.source_widget = source_widget
        # Serializamos la imagen en formato QImage dentro de un QByteArray (no usado directamente, pero útil si se quiere extender)
        ba = QByteArray()
        stream = QDataStream(ba, QIODevice.WriteOnly)
        stream << pixmap.toImage()
        self.setData("application/x-pixmap", ba)

    def image(self):
        return self._pixmap

# =======================
# Widget de Celda del Collage
# =======================

class CollageCell(QFrame):
    """
    Representa una celda del collage.
    Permite arrastrar y soltar imágenes, ya sea cargándolas desde archivos externos o
    intercambiando imágenes entre celdas de la aplicación.
    """
    def __init__(self, cell_id: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap = None  # QPixmap almacenado en esta celda
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setAcceptDrops(True)
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Etiqueta para mostrar la imagen o un texto indicativo
        self.label = QLabel("Drop Image Here", self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: #ddd;")
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        logging.info("Celda %d: creada.", self.cell_id)

    def setImage(self, pixmap: QPixmap):
        self.pixmap = pixmap
        self.label.setPixmap(pixmap.scaled(self.label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logging.info("Celda %d: imagen cargada.", self.cell_id)

    def clearImage(self):
        self.pixmap = None
        self.label.setText("Drop Image Here")
        self.label.setPixmap(QPixmap())

    def updateDisplay(self):
        if self.pixmap:
            self.label.setPixmap(self.pixmap.scaled(self.label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.label.setText("Drop Image Here")

    def resizeEvent(self, event):
        self.updateDisplay()
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.pixmap:
            logging.info("Celda %d: iniciando drag.", self.cell_id)
            drag = QDrag(self)
            mime_data = ImageMimeData(self.pixmap, self)
            drag.setMimeData(mime_data)
            # Usamos una versión reducida del pixmap para la visualización del drag
            drag.setPixmap(self.pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            result = drag.exec(Qt.MoveAction)
            logging.info("Celda %d: drag finalizado (resultado: %s).", self.cell_id, result)

    def dragEnterEvent(self, event):
        logging.debug("Celda %d: dragEnterEvent.", self.cell_id)
        # Aceptar si se trata de un archivo (URL) o si contiene nuestro formato de imagen interno
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        logging.info("Celda %d: dropEvent.", self.cell_id)
        mime = event.mimeData()
        # Caso 1: Drag desde dentro de la aplicación (intercambio de imágenes)
        if mime.hasFormat("application/x-pixmap"):
            source_cell = getattr(mime, "source_widget", None)
            if source_cell and source_cell is not self:
                logging.info("Celda %d: intercambiando imagen con Celda %d.", self.cell_id, source_cell.cell_id)
                self.pixmap, source_cell.pixmap = source_cell.pixmap, self.pixmap
                self.updateDisplay()
                source_cell.updateDisplay()
                event.acceptProposedAction()
                return
        # Caso 2: Arrastrar archivo externo
        elif mime.hasUrls():
            url = mime.urls()[0]
            file_path = url.toLocalFile()
            if file_path:
                logging.info("Celda %d: cargando imagen desde %s", self.cell_id, file_path)
                reader = QImageReader(file_path)
                image = reader.read()
                if image.isNull():
                    logging.error("Celda %d: error al cargar la imagen.", self.cell_id)
                    event.ignore()
                    return
                pixmap = QPixmap.fromImage(image)
                self.setImage(pixmap)
                event.acceptProposedAction()
                return
        event.ignore()

# =======================
# Widget del Collage
# =======================

class CollageWidget(QWidget):
    """
    Widget que organiza en un grid las celdas del collage.
    Permite actualizar el número de filas y columnas y reconstruye la cuadrícula dinámicamente.
    """
    def __init__(self, rows=2, columns=2, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(10)
        self.setLayout(self.grid_layout)
        self.cells = []
        self.populate_grid()

    def populate_grid(self):
        # Limpiar el layout existente
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
                cell = CollageCell(cell_id, self)
                self.grid_layout.addWidget(cell, i, j)
                self.cells.append(cell)
        logging.info("Collage: cuadrícula creada con %d celdas.", total)

    def update_grid(self, rows, columns):
        self.rows = rows
        self.columns = columns
        logging.info("Collage: actualizando a %d filas x %d columnas.", rows, columns)
        self.populate_grid()

# =======================
# Ventana Principal
# =======================

class MainWindow(QMainWindow):
    """
    Ventana principal que orquesta la aplicación.
    Incorpora controles para ajustar filas/columnas, actualizar la cuadrícula y guardar el collage.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker - PySide6")
        self.resize(800, 600)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Controles de interfaz (filas, columnas, botones)
        controls_layout = QHBoxLayout()
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setValue(2)
        self.rows_spin.setPrefix("Filas: ")
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1)
        self.cols_spin.setValue(2)
        self.cols_spin.setPrefix("Columnas: ")
        update_button = QPushButton("Actualizar Collage")
        update_button.clicked.connect(self.update_collage)
        save_button = QPushButton("Guardar Collage")
        save_button.clicked.connect(self.save_collage)
        controls_layout.addWidget(self.rows_spin)
        controls_layout.addWidget(self.cols_spin)
        controls_layout.addWidget(update_button)
        controls_layout.addWidget(save_button)
        main_layout.addLayout(controls_layout)

        # Área del collage
        self.collage = CollageWidget(rows=self.rows_spin.value(), columns=self.cols_spin.value())
        main_layout.addWidget(self.collage)
        logging.info("Ventana principal inicializada.")

    def update_collage(self):
        rows = self.rows_spin.value()
        columns = self.cols_spin.value()
        logging.info("Actualizando collage: %d filas x %d columnas.", rows, columns)
        self.collage.update_grid(rows, columns)

    def save_collage(self):
        logging.info("Guardando collage...")
        pixmap = self.collage.grab()  # Captura la imagen del widget
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar Collage", "", "PNG Files (*.png);;JPEG Files (*.jpg)")
        if file_path:
            if pixmap.save(file_path):
                logging.info("Collage guardado en %s", file_path)
            else:
                logging.error("Error al guardar la imagen.")

# =======================
# Punto de Entrada
# =======================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
