from PySide6.QtCore import Qt, Signal, QSize, QPointF, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QColor, QBrush, QPen
from PySide6.QtWidgets import QWidget, QSpinBox, QAbstractButton, QHBoxLayout, QVBoxLayout, QFrame, QSizePolicy

class ArrowWidget(QAbstractButton):
    """
    A fully custom-painted button.
    Does NOT use QSS for background/borders to ensure absolute pixel-perfect rendering
    without interference from global stylesheets or native styling.
    """
    def __init__(self, arrow_type="up", parent=None):
        super().__init__(parent)
        self._arrow_type = arrow_type
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(False)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 1. Determine State Colors
        bg_color = QColor("#f1f5f9") # Default
        if self.isDown():
            bg_color = QColor("#cbd5e1") # Pressed
        elif self.underMouse():
            bg_color = QColor("#e2e8f0") # Hover
            
        border_color = QColor("#cbd5e1")
        arrow_color = QColor("#0f172a")
        if not self.isEnabled():
            arrow_color = QColor("#9ca3af")
            
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        
        # 2. Draw Background & Borders
        # We need to handle the specific rounded corners manually or via a path.
        # Top Button (Type Up): Radius Top-Right, Line Bottom (Separator), Line Left.
        # Bottom Button (Type Down): Radius Bottom-Right, Line Left.
        
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)
        
        # We'll draw the background shape first.
        # Since we are inside a container that has the border, 
        # but WE are responsible for the Right and Left-of-buttons borders?
        # No, the container is the QFrame ModernSpinBoxFrame with a border.
        # But the buttons are INSIDE. Use transparent brush for corners to be safe?
        # Actually, simpler: Draw the background rect with specific rounded corners.
        
        # Note: adjustRect for 0.5 stroke alignment? 
        # Let's simplify: fill the rect, then draw lines on top.
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg_color))
        
        # Precise Clip Path for Rounded Corners
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(rect), 0, 0) # Default square
        
        if self._arrow_type == "up":
            # Top Right Radius = 5px
            # We can construct a specific path:
            # Start Top Left -> Top Right (Arc) -> Bottom Right -> Bottom Left -> Close
            path.moveTo(0, 0)
            path.lineTo(w - 6, 0) # Stop before corner
            path.arcTo(w - 12, 0, 12, 12, 90, -90) # Top Right Corner
            path.lineTo(w, h)
            path.lineTo(0, h)
            path.lineTo(0, 0)
        else:
            # Bottom Right Radius = 5px
            path.moveTo(0, 0)
            path.lineTo(w, 0)
            path.lineTo(w, h - 6) # Stop before corner
            path.arcTo(w - 12, h - 12, 12, 12, 0, -90) # Bottom Right Corner
            path.lineTo(0, h)
            path.lineTo(0, 0)
            
        painter.drawPath(path)
        
        # 3. Draw Borders (Lines)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(Qt.NoBrush)
        
        # Left Border (Always)
        painter.drawLine(0, 0, 0, h)
        
        if self._arrow_type == "up":
            # Bottom Border (Separator)
            painter.drawLine(0, h - 1, w, h - 1)
            
        # 4. Draw Arrow
        # Centering logic
        cx = w / 2
        cy = h / 2
        
        # Manual Nudge: The user felt they were "too low" or "stuck".
        # Let's nudge UP by 0.5px or 1px just to be safe.
        nudge_y = -0.5 
        
        arrow_path = QPainterPath()
        aw = 8 # Arrow Width
        ah = 5 # Arrow Height
        
        if self._arrow_type == "up":
            # Tip Top
            # Center of arrow is cy + nudge
            # Tip: (cx, cy - ah/2 + nudge)
            base_y = cy + nudge_y
            arrow_path.moveTo(cx, base_y - ah/2)
            arrow_path.lineTo(cx - aw/2, base_y + ah/2)
            arrow_path.lineTo(cx + aw/2, base_y + ah/2)
        else:
            # Tip Bottom
            base_y = cy + nudge_y
            arrow_path.moveTo(cx, base_y + ah/2)
            arrow_path.lineTo(cx - aw/2, base_y - ah/2)
            arrow_path.lineTo(cx + aw/2, base_y - ah/2)
            
        arrow_path.closeSubpath()
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(arrow_color))
        painter.drawPath(arrow_path)


class ModernSpinBox(QFrame):
    """
    A composite SpinBox that draws a single unified border around a transparent
    input field and buttons, ensuring a perfect fused look with no gaps.
    """
    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setFixedWidth(70) 
        
        # 1. Container Style (The one true border)
        self.setObjectName("ModernSpinBoxFrame")
        self.setStyleSheet("""
            #ModernSpinBoxFrame {
                background-color: white;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                /* Ensure no internal padding messes us up */
                padding: 0px;
            }
        """)
        
        # Layout: Horizontal, no spacing
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 2. Input Field
        self._spin = QSpinBox()
        self._spin.setButtonSymbols(QSpinBox.NoButtons)
        self._spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # We need to make sure the input text aligns nicely
        self._spin.setStyleSheet("""
            QSpinBox {
                border: none;
                background: transparent;
                color: #111827;
                padding-left: 4px; 
                margin: 0;
            }
        """)
        self._spin.valueChanged.connect(self.valueChanged.emit)
        
        # 3. Button Container
        btn_container = QWidget()
        btn_container.setFixedWidth(20)
        btn_container.setFixedHeight(30) 
        # Important: transparent background for container
        btn_container.setStyleSheet("background: transparent; border: none;")
        
        v_layout = QVBoxLayout(btn_container)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(0)
        
        # 4. Custom Painted Buttons
        # Total height available inside the 1px border of 30px frame is roughly 28px.
        # So 14px each is correct.
        
        self._btn_up = ArrowWidget("up") 
        self._btn_up.clicked.connect(self._spin.stepUp)
        self._btn_up.setFixedHeight(14)
        
        self._btn_down = ArrowWidget("down") 
        self._btn_down.clicked.connect(self._spin.stepDown)
        self._btn_down.setFixedHeight(14)
        
        v_layout.addWidget(self._btn_up)
        v_layout.addWidget(self._btn_down)
        
        layout.addWidget(self._spin)
        layout.addWidget(btn_container)

    # Proxy Methods -----------------------------------------------------------
    def setValue(self, val: int):
        self._spin.setValue(val)
        
    def value(self) -> int:
        return self._spin.value()
        
    def setRange(self, min_val: int, max_val: int):
        self._spin.setRange(min_val, max_val)
        
    def setToolTip(self, text: str):
        self._spin.setToolTip(text)
        self._btn_up.setToolTip(text)
        self._btn_down.setToolTip(text)
