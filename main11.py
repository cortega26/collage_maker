import sys
import logging
import traceback

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QSpinBox,
    QHBoxLayout, QPushButton, QFileDialog, QInputDialog, QCheckBox, QLabel,
    QComboBox
)
from PySide6.QtCore import Qt, QMimeData, QByteArray, QDataStream, QIODevice, QRect, QSize, QPoint
from PySide6.QtGui import QDrag, QPixmap, QPainter, QImageReader, QColor, QImage

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
        
        rect = self.rect()  # área completa de la celda
        if self.pixmap:
            # Escalar y centrar la imagen con mejor calidad
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
                # Configurar fuente según la opción de formato personalizado
                font = painter.font()
                if self.use_caption_formatting:
                    font.setPointSize(self.caption_font_size)
                    font.setBold(self.caption_bold)
                    font.setItalic(self.caption_italic)
                    font.setUnderline(self.caption_underline)
                else:
                    # Fuente básica sin formato extra
                    font.setPointSize(12)
                    font.setBold(False)
                    font.setItalic(False)
                    font.setUnderline(False)
                painter.setFont(font)
                # Calcular el rectángulo justo detrás del texto
                metrics = painter.fontMetrics()
                text_rect = metrics.boundingRect(self.caption)
                # Centrar horizontalmente en la parte inferior con algo de margen
                text_rect.moveCenter(QPoint(rect.center().x(), rect.bottom() - text_rect.height()//2 - 5))
                # Agregar padding al fondo del texto
                background_rect = text_rect.adjusted(-4, -2, 4, 2)
                # Dibujar fondo discreto semitransparente
                painter.fillRect(background_rect, QColor(0, 0, 0, 100))
                # Dibujar el texto en amarillo
                painter.setPen(Qt.yellow)
                painter.drawText(text_rect, Qt.AlignCenter, self.caption)
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
            # Use smoother scaling for the drag preview
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
            reader = QImageReader(file_path)
            # Optimizar la carga de imágenes
            reader.setAutoTransform(True)  # Apply EXIF orientation
            
            # WEBP specific optimizations
            if file_path.lower().endswith('.webp'):
                reader.setQuality(100)  # Use maximum quality for WebP
            
            # Si es una imagen muy grande, utilizamos preescalado para mejorar rendimiento
            max_dimension = 2000  # Set a reasonable max dimension for memory efficiency
            if reader.canRead():
                image_size = reader.size()
                if image_size.width() > max_dimension or image_size.height() > max_dimension:
                    scale_factor = max_dimension / max(image_size.width(), image_size.height())
                    new_size = image_size * scale_factor
                    reader.setScaledSize(new_size.toSize())
            
            image = reader.read()
            if image.isNull():
                raise ValueError("Imagen inválida o con formato no soportado.")
                
            # Convert to 32-bit ARGB format for better quality
            if image.format() != QImage.Format_ARGB32:
                image = image.convertToFormat(QImage.Format_ARGB32)
                
            self.setImage(QPixmap.fromImage(image))
            event.acceptProposedAction()
        except Exception as e:
            logging.error("Celda %d: Error al cargar la imagen: %s", self.cell_id, e)
            event.ignore()

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
        if not self.is_valid_merge(start_row, start_col, row_span, col_span):
            logging.warning("Invalid merge request: cells already merged or out of bounds")
            return False

        # Get the target cell
        cell_index = start_row * self.columns + start_col
        if cell_index >= len(self.cells):
            return False

        target_cell = self.cells[cell_index]
        
        # Remove cells that will be merged
        cells_to_remove = []
        for r in range(start_row, start_row + row_span):
            for c in range(start_col, start_col + col_span):
                if r == start_row and c == start_col:
                    continue
                idx = r * self.columns + c
                if idx < len(self.cells):
                    cells_to_remove.append(self.cells[idx])

        # Remove widgets from layout and list
        for cell in cells_to_remove:
            self.grid_layout.removeWidget(cell)
            cell.hide()
            self.cells.remove(cell)

        # Update the target cell
        self.grid_layout.removeWidget(target_cell)
        target_cell.setSpan(row_span, col_span)
        self.grid_layout.addWidget(target_cell, start_row, start_col, row_span, col_span)
        
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
            return False

        # Check if any cell in the range is already part of a merge
        for r in range(start_row, start_row + row_span):
            for c in range(start_col, start_col + col_span):
                if self.is_cell_merged(r, c):
                    return False
        return True

    def is_cell_merged(self, row: int, col: int) -> bool:
        """Check if a cell is part of any merged region."""
        for (start_row, start_col), (row_span, col_span) in self.merged_cells.items():
            if (start_row <= row < start_row + row_span and 
                start_col <= col < start_col + col_span):
                return True
        return False

    def split_merged_cell(self, row: int, col: int):
        """Split a merged cell back into individual cells."""
        if (row, col) not in self.merged_cells:
            return

        row_span, col_span = self.merged_cells[(row, col)]
        target_cell = None

        # Find the merged cell widget
        for cell in self.cells:
            if cell.row_span > 1 or cell.col_span > 1:
                cell_pos = self.grid_layout.getItemPosition(self.grid_layout.indexOf(cell))
                if cell_pos[:2] == (row, col):
                    target_cell = cell
                    break

        if target_cell:
            # Remove the merged cell
            self.grid_layout.removeWidget(target_cell)
            target_cell.setSpan(1, 1)  # Reset span
            
            # Recreate individual cells
            for r in range(row, row + row_span):
                for c in range(col, col + col_span):
                    if r == row and c == col:
                        # Reuse the target cell for the first position
                        self.grid_layout.addWidget(target_cell, r, c, 1, 1)
                    else:
                        # Create new cells for other positions
                        cell_id = r * self.columns + c
                        new_cell = CollageCell(cell_id, self.cell_size, self)
                        self.grid_layout.addWidget(new_cell, r, c, 1, 1)
                        self.cells.append(new_cell)

        # Remove merge information
        del self.merged_cells[(row, col)]
        logging.info(f"Split merged cell at ({row},{col})")

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

# ========================================================
# Ventana Principal
# ========================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker - PySide6")
        self.resize(850, 650)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.addLayout(self.create_controls_panel())
        self.collage = CollageWidget(rows=self.rows_spin.value(), columns=self.cols_spin.value(), cell_size=260)
        main_layout.addWidget(self.collage, alignment=Qt.AlignCenter)
        logging.info("Ventana principal inicializada.")

    def create_controls_panel(self):
        controls_layout = QHBoxLayout()

        # Grid controls
        grid_controls = QHBoxLayout()
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setValue(2)
        self.rows_spin.setPrefix("Rows: ")
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1)
        self.cols_spin.setValue(2)
        self.cols_spin.setPrefix("Columns: ")

        update_button = QPushButton("Update Grid")
        update_button.clicked.connect(self.update_collage)
        save_button = QPushButton("Save Collage")
        save_button.clicked.connect(self.save_collage)

        grid_controls.addWidget(self.rows_spin)
        grid_controls.addWidget(self.cols_spin)
        grid_controls.addWidget(update_button)
        grid_controls.addWidget(save_button)

        # Cell merging controls
        merge_controls = QHBoxLayout()
        merge_label = QLabel("Merge cells:")
        self.merge_row_spin = QSpinBox()
        self.merge_row_spin.setMinimum(0)
        self.merge_row_spin.setMaximum(9)
        self.merge_row_spin.setPrefix("Row: ")
        
        self.merge_col_spin = QSpinBox()
        self.merge_col_spin.setMinimum(0)
        self.merge_col_spin.setMaximum(9)
        self.merge_col_spin.setPrefix("Col: ")
        
        self.merge_rowspan_spin = QSpinBox()
        self.merge_rowspan_spin.setMinimum(1)
        self.merge_rowspan_spin.setMaximum(4)
        self.merge_rowspan_spin.setValue(2)
        self.merge_rowspan_spin.setPrefix("Row span: ")
        
        self.merge_colspan_spin = QSpinBox()
        self.merge_colspan_spin.setMinimum(1)
        self.merge_colspan_spin.setMaximum(4)
        self.merge_colspan_spin.setValue(2)
        self.merge_colspan_spin.setPrefix("Col span: ")

        merge_button = QPushButton("Merge")
        merge_button.clicked.connect(self.merge_cells)
        split_button = QPushButton("Split")
        split_button.clicked.connect(self.split_cells)

        merge_controls.addWidget(merge_label)
        merge_controls.addWidget(self.merge_row_spin)
        merge_controls.addWidget(self.merge_col_spin)
        merge_controls.addWidget(self.merge_rowspan_spin)
        merge_controls.addWidget(self.merge_colspan_spin)
        merge_controls.addWidget(merge_button)
        merge_controls.addWidget(split_button)

        # Image quality controls
        quality_layout = QHBoxLayout()
        quality_label = QLabel("Image Quality:")
        
        self.transform_combo = QComboBox()
        self.transform_combo.addItem("High Quality", Qt.SmoothTransformation)
        self.transform_combo.addItem("Balanced", Qt.SmoothTransformation)
        self.transform_combo.addItem("Fast", Qt.FastTransformation)
        self.transform_combo.setCurrentIndex(0)
        self.transform_combo.currentIndexChanged.connect(self.update_image_quality)
        
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItem("Keep Aspect Ratio", Qt.KeepAspectRatio)
        self.aspect_combo.addItem("Stretch to Fill", Qt.IgnoreAspectRatio)
        self.aspect_combo.addItem("Fit Inside", Qt.KeepAspectRatioByExpanding)
        self.aspect_combo.setCurrentIndex(0)
        self.aspect_combo.currentIndexChanged.connect(self.update_image_quality)
        
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.transform_combo)
        quality_layout.addWidget(self.aspect_combo)

        # Caption formatting controls
        caption_controls = QHBoxLayout()
        caption_label = QLabel("Caption Format:")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 36)
        self.font_size_spin.setValue(14)
        self.font_size_spin.setPrefix("Size: ")
        self.font_size_spin.valueChanged.connect(self.update_caption_format)

        self.bold_checkbox = QCheckBox("Bold")
        self.bold_checkbox.setChecked(True)
        self.bold_checkbox.toggled.connect(self.update_caption_format)

        self.italic_checkbox = QCheckBox("Italic")
        self.italic_checkbox.setChecked(False)
        self.italic_checkbox.toggled.connect(self.update_caption_format)

        self.underline_checkbox = QCheckBox("Underline")
        self.underline_checkbox.setChecked(False)
        self.underline_checkbox.toggled.connect(self.update_caption_format)

        caption_controls.addWidget(caption_label)
        caption_controls.addWidget(self.font_size_spin)
        caption_controls.addWidget(self.bold_checkbox)
        caption_controls.addWidget(self.italic_checkbox)
        caption_controls.addWidget(self.underline_checkbox)

        # Organize all controls vertically
        controls_vertical = QVBoxLayout()
        controls_vertical.addLayout(grid_controls)
        controls_vertical.addLayout(merge_controls)
        controls_vertical.addLayout(quality_layout)
        controls_vertical.addLayout(caption_controls)
        
        return controls_vertical

    def merge_cells(self):
        """Handle the merge cells button click."""
        row = self.merge_row_spin.value()
        col = self.merge_col_spin.value()
        row_span = self.merge_rowspan_spin.value()
        col_span = self.merge_colspan_spin.value()
        
        if self.collage.merge_cells(row, col, row_span, col_span):
            logging.info(f"Cells merged successfully at ({row},{col}) with span {row_span}x{col_span}")
        else:
            logging.warning(f"Could not merge cells at ({row},{col})")

    def split_cells(self):
        """Handle the split cells button click."""
        row = self.merge_row_spin.value()
        col = self.merge_col_spin.value()
        self.collage.split_merged_cell(row, col)

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

    def update_image_quality(self):
        # Actualizar configuración de calidad para todas las celdas
        transform_mode = self.transform_combo.currentData()
        aspect_mode = self.aspect_combo.currentData()
        
        for cell in self.collage.cells:
            cell.transformation_mode = transform_mode
            cell.aspect_ratio_mode = aspect_mode
            cell.update()
            
        logging.info("Calidad de imagen actualizada: transformación=%s, aspecto=%s",
                    self.transform_combo.currentText(), self.aspect_combo.currentText())

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
            format = file_path.split('.')[-1].lower()
            quality = 100  # Máxima calidad por defecto
            
            if format in ['jpg', 'jpeg']:
                if not high_res_pixmap.save(file_path, format, quality):
                    raise IOError("No se pudo guardar la imagen JPEG.")
            elif format == 'webp':
                if not high_res_pixmap.save(file_path, format, quality):
                    raise IOError("No se pudo guardar la imagen WebP.")
            else:  # png y otros
                if not high_res_pixmap.save(file_path):
                    raise IOError("No se pudo guardar la imagen.")
                    
            logging.info("Collage guardado en %s con alta calidad", file_path)
            
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