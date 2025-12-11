
import pytest
from unittest.mock import MagicMock, call
from src.presenter import CollagePresenter

@pytest.fixture
def mock_view():
    view = MagicMock()
    # Mock specific attributes accessed by presenter
    view.collage = MagicMock()
    view.collage.rows = 2
    view.collage.columns = 2
    view.collage.cells = []
    
    view.rows_spin = MagicMock()
    view.cols_spin = MagicMock()
    view.template_combo = MagicMock()
    
    view.top_visible_chk = MagicMock()
    view.bottom_visible_chk = MagicMock()
    view.font_combo = MagicMock()
    view.font_size_spin = MagicMock()
    view.stroke_width_spin = MagicMock()
    view.uppercase_chk = MagicMock()
    
    return view

@pytest.fixture
def presenter(mock_view):
    return CollagePresenter(mock_view)

def test_update_grid_delegates_to_collage(presenter, mock_view):
    """Verify update_grid calls collage.update_grid correctly."""
    presenter.update_grid(3, 4)
    
    mock_view.collage.update_grid.assert_called_once_with(3, 4)
    mock_view._capture_for_undo.assert_called_once()
    mock_view._update_history_baseline.assert_called_once()

def test_get_collage_state_assembles_dict(presenter, mock_view):
    """Verify get_collage_state collects data from widgets."""
    mock_view.collage.serialize_for_autosave.return_value = {"grid": "data"}
    mock_view.rows_spin.value.return_value = 5
    mock_view.cols_spin.value.return_value = 5
    mock_view.template_combo.currentText.return_value = "5x5"
    mock_view.font_size_spin.value.return_value = 12
    
    state = presenter.get_collage_state()
    
    assert state['collage'] == {"grid": "data"}
    assert state['controls']['rows'] == 5
    assert state['controls']['columns'] == 5
    assert state['captions']['font_size'] == 12

def test_apply_template_updates_spins_and_grid(presenter, mock_view):
    """Verify apply_template parses string and updates view."""
    # Since apply_template calls update_grid, we can check side effects
    
    # Need to simulate spin box change causing update_grid if not blocked?
    # In this implementation, presenter calls update_grid explicitly inside apply_template?
    # Wait, my implementation called self.update_grid explicitly.
    
    presenter.apply_template("3x4")
    
    mock_view.rows_spin.setValue.assert_called_with(3)
    mock_view.cols_spin.setValue.assert_called_with(4)
    mock_view.collage.update_grid.assert_called_with(3, 4)

def test_reset_collage_clears_if_content(presenter, mock_view):
    """Verify reset_collage calls clear() when content exists."""
    # Mock content
    cell = MagicMock()
    cell.pixmap = "exists"
    mock_view.collage.cells = [cell]
    
    presenter.reset_collage()
    
    mock_view.collage.clear.assert_called_once()
    mock_view._capture_for_undo.assert_called_once()
