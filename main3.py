import sys
import logging
from datetime import datetime

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
# Clase personalizada para manejar datos de imagen en drag
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
# Widget de cada celda del collage
# ========================================================

class CollageCell(QWidget):
    """
    Cada celda se dibuja en un área cuadrada perfecta.
    La celda indica que su altura depende de su ancho para que el layout la ajuste como cuadrado.
    """
    def __init__(self, cell_id: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.pixmap = None  # QPixmap actualmente cargado
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background-color: transparent;")
        logging.info("Celda %d creada.", self.cell_id)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return width

    def setImage(self, pixmap: QPixmap):
        self.pixmap = pixmap
        self.update()  # Fuerza redibujado
        logging.info("Celda %d: imagen cargada.", self.cell_id)

    def clearImage(self):
        self.pixmap = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()
        # Calculamos un cuadrado perfecto que ocupe todo el ancho disponible
        square = QRect(0, 0, rect.width(), rect.width())
        # Centramos verticalmente el cuadrado dentro de la celda
        square.moveTop((rect.height() - rect.width()) // 2)
        if self.pixmap:
            # Escalar la imagen manteniendo su proporción (KeepAspectRatio)
            scaled = self.pixmap.scaled(square.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            # Centrar la imagen en el cuadrado
            x = square.x() + (square.width() - scaled.width()) // 2
            y = square.y() + (square.height() - scaled.height()) // 2
            target = QRect(x, y, scaled.width(), scaled.height())
            painter.drawPixmap(target, scaled, scaled.rect())
        else:
            painter.fillRect(square, Qt.white)
            painter.setPen(Qt.gray)
            painter.drawText(square, Qt.AlignCenter, "Drop Image Here")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.pixmap:
            logging.info("Celda %d: iniciando drag.", self.cell_id)
            drag = QDrag(self)
            mime_data = ImageMimeData(self.pixmap, self)
            drag.setMimeData(mime_data)
            drag.setPixmap(self.pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
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
                logging.info("Celda %d: cargando imagen desde %s", self.cell_id, file_path)
                reader = QImageReader(file_path)
                image = reader.read()
                if image.isNull():
                    logging.error("Celda %d: error al cargar la imagen.", self.cell_id)
                    event.ignore()
                    return
                self.setImage(QPixmap.fromImage(image))
                event.acceptProposedAction()
                return
        event.ignore()

# ========================================================
# Widget del Collage: organiza las celdas en un grid.
# ========================================================

class CollageWidget(QWidget):
    def __init__(self, rows=2, columns=2, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.columns = columns
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(2)  # margen de 2 píxeles
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.grid_layout)
        self.setStyleSheet("background-color: black;")
        self.cells = []
        self.populate_grid()

    def populate_grid(self):
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
        logging.info("Collage: creado con %d celdas.", total)

    def update_grid(self, rows, columns):
        self.rows = rows
        self.columns = columns
        logging.info("Collage: actualizando a %d filas x %d columnas.", rows, columns)
        self.populate_grid()

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
        pixmap = self.collage.grab()
        file_path, _ = QFileDialog.getSaveFileName(self, "Guardar Collage", "", "PNG Files (*.png);;JPEG Files (*.jpg)")
        if file_path:
            if pixmap.save(file_path):
                logging.info("Collage guardado en %s", file_path)
            else:
                logging.error("Error al guardar la imagen.")

# ========================================================
# Punto de Entrada
# ========================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
