
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QWidget
from src.widgets.collage import CollageWidget
from src.widgets.cell import CollageCell
from src.managers.performance import PerformanceMonitor

@pytest.fixture
def app():
    if not QApplication.instance():
        return QApplication([])
    return QApplication.instance()

def test_optimize_memory_propagation(app):
    """PERF-001: Validate optimize_memory calls propagate to cells."""
    collage = CollageWidget(rows=2, columns=2)
    # Mock cells manually
    mock_cells = [MagicMock(), MagicMock()]
    collage.cells = mock_cells

    collage.optimize_memory()

    for cell in mock_cells:
        cell.optimize_memory.assert_called_once()

def test_performance_monitor_triggers_optimization(app):
    """PERF-001: Validate PerformanceMonitor calls parent.collage.optimize_memory."""
    # Use real QWidget to satisfy QTimer(parent) type check
    real_parent = QWidget()
    real_parent.collage = MagicMock()
    
    # Patch QTimer to avoid actual timers running
    with patch('src.managers.performance.QTimer'):
        monitor = PerformanceMonitor(real_parent)
    
        # Force optimization
        with patch('src.managers.performance.psutil') as mock_psutil:
            mock_psutil.Process.return_value.memory_info.return_value.rss = 10**12 # High memory
            with patch('src.managers.performance.get_cache'):
                monitor._optimize()
            
    real_parent.collage.optimize_memory.assert_called_once()

def test_async_image_loading_uses_worker(app, tmp_path):
    """PERF-002: Validate _load_image uses QThreadPool."""
    cell = CollageCell(1)
    
    # Create dummy image
    img_path = tmp_path / "test.png"
    with open(img_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
        
    import logging
    # We need to patch where QThreadPool is defined/imported.
    # Since it is imported inside the method in cell.py:
    # from PySide6.QtCore import QThreadPool
    # We can patch 'PySide6.QtCore.QThreadPool.globalInstance'
    
    with patch('PySide6.QtCore.QThreadPool.globalInstance') as mock_pool_instance:
        with patch('src.widgets.cell.logging.error') as mock_log:
            cell._load_image(str(img_path))
            
            if mock_log.called:
                 raise RuntimeError(f"Caught logged error: {mock_log.call_args}")

        # Should start a worker
        mock_pool_instance.return_value.start.assert_called_once()
        
    assert cell._is_loading is True
