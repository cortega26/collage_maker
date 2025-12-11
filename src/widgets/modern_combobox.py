from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QPainterPath, QColor, QBrush, QPen, QFontMetrics, QFontDatabase, QFont
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionComboBox, QStyledItemDelegate, QListView

class LimitedListView(QListView):
    """
    A QListView that caps its own preferred height.
    Crucial for preventing the 'Black Void' rendering artifact.
    """
    def sizeHint(self):
        s = super().sizeHint()
        # Cap height at 450px (exactly 15 items * 30px)
        if s.height() > 450:
            s.setHeight(450)
        return s

class FontDelegate(QStyledItemDelegate):
    """
    Delegate to ensure consistent row heights in the font dropdown.
    Prevents 'Full Screen' popups caused by erratic font metrics.
    """
    def sizeHint(self, option, index):
        # Enforce a fixed, comfortable height for all items
        return QSize(0, 30)

    def paint(self, painter, option, index):
        # Standard painting but ensures we respect the fixed rect
        painter.save()
        
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#4f46e5"))
            painter.setPen(Qt.white)
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor("#e0e7ff"))
            painter.setPen(QColor("#111827"))
        else:
            painter.fillRect(option.rect, Qt.white)
            painter.setPen(QColor("#111827"))
            
        font = index.data(Qt.FontRole)
        if not font:
            font = QFont()
        
        font.setPointSize(12) 
        painter.setFont(font)
        
        text = index.data(Qt.DisplayRole)
        
        rect = option.rect
        rect.setLeft(rect.left() + 8) 
        
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.restore()

class ModernComboBox(QComboBox):
    """
    A custom-painted QComboBox that guarantees pixel-perfect rendering.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 1. VIEW: Caps the total rendering height.
        view = LimitedListView(self)
        self.setView(view)
        
        # 2. DELEGATE: Caps the individual row height.
        self.setItemDelegate(FontDelegate(self))
        
        # Sizing
        self.setMinimumHeight(32)
        self.setMaxVisibleItems(15)
        
        # Scrollbar Logic
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Styling: Internal spacing & Scrollbar
        self.view().setStyleSheet("""
            QListView { 
                padding: 0px; 
                border: 1px solid #d1d5db;
                background-color: white;
                outline: none;
            }
            QScrollBar:vertical {
                border: none;
                background: white;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #e5e7eb;
                min-height: 30px;
                border-radius: 5px;
                border: 2px solid white;
            }
            QScrollBar::handle:vertical:hover {
                background: #d1d5db;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        
        # 1. Geometry & Colors
        rect = self.rect()
        w, h = rect.width(), rect.height()
        
        bg_color = QColor("white")
        border_color = QColor("#d1d5db") # Gray-300
        text_color = QColor("#111827")   # Gray-900
        arrow_color = QColor("#334155")  # Slate-700
        
        if self.hasFocus():
             border_color = QColor("#6366f1") # Indigo-500 ring
        
        # 2. Draw Frame / Background
        # Adjust for 1px border
        frame_rect = QRectF(0.5, 0.5, w - 1, h - 1)
        radius = 6
        
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(frame_rect, radius, radius)
        
        # 3. Draw Separator Line (Skipped)
        
        # 4. Draw Arrow (Right Aligned)
        # Area for arrow: 30px w
        arrow_area_w = 30
        arrow_x_start = w - arrow_area_w
        
        # Vector Triangle: Down pointing
        # Center of arrow area
        cx = arrow_x_start + (arrow_area_w / 2)
        cy = h / 2
        
        # Size: 10px wide, 6px high
        half_w = 4
        half_h = 3
        
        arrow_path = QPainterPath()
        # Top Left
        p1 = QPointF(cx - half_w, cy - half_h + 1)
        # Top Right
        p2 = QPointF(cx + half_w, cy - half_h + 1)
        # Bottom Center
        p3 = QPointF(cx, cy + half_h + 1)
        
        arrow_path.moveTo(p1)
        arrow_path.lineTo(p2)
        arrow_path.lineTo(p3)
        arrow_path.closeSubpath()
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(arrow_color))
        painter.drawPath(arrow_path)
        
        # 5. Draw Text (Clipped to not overlap arrow)
        text_rect = rect.adjusted(10, 0, -arrow_area_w, 0)
        painter.setPen(text_color)
        
        # Get text from current index
        current_text = self.currentText()
        
        # Elide if too long
        fm = self.fontMetrics()
        elided_text = fm.elidedText(current_text, Qt.ElideRight, text_rect.width())
        
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_text)

    # Populate helper for Fonts since we replace QFontComboBox
    def populate_fonts(self):
        db = QFontDatabase()
        families = db.families()
        self.clear()
        for family in families:
            # DirectWrite Fix: Filter out legacy bitmap fonts (Fixedsys, Terminal, etc.)
            # These cause 'CreateFontFaceFromHDC() failed' errors and render poorly.
            if not db.isSmoothlyScalable(family):
                continue
                
            self.addItem(family)
            # Set font for the item to render in its own style
            # Index of the item we just added is count() - 1
            idx = self.count() - 1
            # We don't strictly need setPointSize here as the Delegate handles it
            self.setItemData(idx, QFont(family), Qt.FontRole)

    # QFontComboBox Compatibility Methods
    def currentFont(self):
        """Returns the currently selected QFont."""
        font = self.itemData(self.currentIndex(), Qt.FontRole)
        # If no font data is set (unlikely), fall back to creating one from text
        if not isinstance(font, QFont):
            font = QFont(self.currentText())
        return font

    def setCurrentFont(self, font):
        """Sets the current index to the item matching the given QFont family."""
        if not isinstance(font, QFont):
            return
        index = self.findText(font.family())
        if index != -1:
            self.setCurrentIndex(index)
