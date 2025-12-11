from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QPainterPath, QColor, QBrush, QPen, QFontMetrics
from PySide6.QtWidgets import QCheckBox, QStyleOptionButton, QStyle

class ModernCheckBox(QCheckBox):
    """
    A custom-painted QCheckBox that completely bypasses the native style engine
    to guarantee the 'modern styling' (Filled Square + White Checkmark).
    """
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        # We handle spacing manually in paintEvent, but setting it helps sizing hints
        self.setStyleSheet("spacing: 8px;") 

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 1. Colors & Dimensions
        box_size = 18
        radius = 4
        
        # Text Color
        text_color = QColor("#334155") # Slate-700
        
        # Box Colors
        bg_color = QColor("white")
        border_color = QColor("#cbd5e1") # Slate-300
        
        if self.isChecked():
            bg_color = QColor("#334155") # Slate-700
            border_color = QColor("#334155")
        
        if self.underMouse():
            if self.isChecked():
                 bg_color = QColor("#1e293b") # Slate-800
                 border_color = QColor("#1e293b")
            else:
                 border_color = QColor("#94a3b8") # Slate-400
                 bg_color = QColor("#f8fafc")

        # 2. Draw Box
        # Vertically center the box
        rect = self.rect()
        h = rect.height()
        y_offset = (h - box_size) / 2
        
        box_rect = QRectF(0, y_offset, box_size, box_size)
        
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(box_rect, radius, radius)
        
        # 3. Draw Checkmark (if checked)
        if self.isChecked():
            check_path = QPainterPath()
            # Geometry for 18x18 box
            # Polyline: 3,9 -> 7,13 -> 15,5 (Approximate relative to 0,0)
            # Scaled slightly to fit nicely
            
            # Start: x=4, y=9
            # Mid:   x=8, y=13
            # End:   x=14, y=5
            
            origin = box_rect.topLeft()
            p1 = origin + QPointF(4, 9.5)
            p2 = origin + QPointF(7.5, 13)
            p3 = origin + QPointF(14, 5)
            
            check_path.moveTo(p1)
            check_path.lineTo(p2)
            check_path.lineTo(p3)
            
            painter.setPen(QPen(QColor("white"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(check_path)
            
        # 4. Draw Text
        # Offset text by box width + spacing
        spacing = 8
        text_x = box_size + spacing
        text_rect = QRectF(text_x, 0, rect.width() - text_x, h)
        
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())

    def sizeHint(self):
        # Calculate exact size needed for our custom painting
        spacing = 8
        box_size = 18
        
        fm = QFontMetrics(self.font())
        text_width = fm.horizontalAdvance(self.text())
        text_height = fm.height()
        
        # Width: Box + Spacing + Text + Safety Margin
        w = box_size + spacing + text_width + 4 
        h = max(box_size, text_height)
        
        return QSize(w, h)

    def minimumSizeHint(self):
        return self.sizeHint()
