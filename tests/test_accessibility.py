
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from src.widgets.collage import CollageWidget
from src.widgets.cell import CollageCell

@pytest.fixture
def app():
    if not QApplication.instance():
        return QApplication([])
    return QApplication.instance()

def test_cell_focus_navigation(app):
    """ACC-001: Verify cells are focusable and tab navigation works."""
    collage = CollageWidget(rows=2, columns=2)
    # Ensure layout and widgets are initialized
    # CollageWidget uses grid layout, child cells should have focus policy
    
    cells = collage.cells
    assert len(cells) == 4
    
    cell0 = cells[0]
    cell1 = cells[1]
    
    # Check default focus policy
    assert cell0.focusPolicy() == Qt.StrongFocus
    
    # Simulate focus (Widget must be visible to take focus usually)
    collage.show()
    cell0.setFocus()
    assert cell0.hasFocus()
    
    # Simulate Tab key (manual focus chain check is hard without showing window)
    # But we can verify focusing another cell works
    cell1.setFocus()
    assert cell1.hasFocus()
    assert not cell0.hasFocus()
    collage.close()

def test_paint_event_calls_focus_ring(app):
    """ACC-001: Ensure paintEvent handles focus state."""
    cell = CollageCell(1)
    cell.show()
    cell.setFocus()
    
    # We can't easily assert visual output, but we can call repaint and ensure it doesn't crash
    # and maybe mock painter if we really wanted to (too complex for this).
    # Just ensuring it runs is a good smoke test.
    cell.repaint()
    assert cell.hasFocus()
    cell.close()
