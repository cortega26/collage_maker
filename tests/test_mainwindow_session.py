import os
from collections.abc import Callable
from pathlib import Path
from typing import List, Tuple

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip(
    "PySide6.QtWidgets",
    reason="PySide6 Qt bindings required for MainWindow session tests",
    exc_type=ImportError,
)

from PySide6.QtWidgets import QApplication  # noqa: E402

import src.main as main_module  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def main_window_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, qt_app: QApplication
) -> Tuple[Callable[[], main_module.MainWindow], List[dict]]:
    autosave_payloads: List[dict] = []

    class StubAutosaveManager:
        def __init__(self, parent, save_callback):
            self.parent = parent
            self.save_callback = save_callback
            self.path = tmp_path / "autosave"
            self.path.mkdir(parents=True, exist_ok=True)

        def perform_autosave(self):
            payload = self.save_callback()
            autosave_payloads.append(payload)
            return payload

    class StubPerformanceMonitor:
        def __init__(self, parent):
            self.parent = parent
            self.timer = None

        def check_memory(self):
            return None

    class StubErrorRecoveryManager:
        def __init__(self, parent, save_state, reset_callback):
            self.parent = parent
            self.save_state = save_state
            self.reset_callback = reset_callback
            self.invocations: List[Tuple[Exception, str]] = []

        def handle_error(self, error: Exception, context: str) -> None:
            self.invocations.append((error, context))

    monkeypatch.setattr(main_module, "AutosaveManager", StubAutosaveManager)
    monkeypatch.setattr(main_module, "PerformanceMonitor", StubPerformanceMonitor)
    monkeypatch.setattr(main_module, "ErrorRecoveryManager", StubErrorRecoveryManager)

    created: List[main_module.MainWindow] = []

    def factory() -> main_module.MainWindow:
        window = main_module.MainWindow()
        created.append(window)
        return window

    yield factory, autosave_payloads

    for window in created:
        window.close()


def test_mainwindow_undo_redo_restores_cell_state(main_window_factory):
    create_window, _ = main_window_factory
    window = create_window()

    first_cell = window.collage.get_cell_at(0, 0)
    assert first_cell is not None

    window._capture_for_undo()
    first_cell.caption = "After"
    first_cell.top_caption = "Topper"
    first_cell.bottom_caption = "Lower"
    window._update_history_baseline()

    window._undo()
    cell_after_undo = window.collage.get_cell_at(0, 0)
    assert cell_after_undo is not None
    assert cell_after_undo.caption == ""
    assert cell_after_undo.top_caption == ""
    assert cell_after_undo.bottom_caption == ""

    window._redo()
    cell_after_redo = window.collage.get_cell_at(0, 0)
    assert cell_after_redo is not None
    assert cell_after_redo.caption == "After"
    assert cell_after_redo.top_caption == "Topper"
    assert cell_after_redo.bottom_caption == "Lower"


def test_mainwindow_restore_state_roundtrip(main_window_factory):
    create_window, _ = main_window_factory
    window = create_window()

    window.rows_spin.setValue(3)
    window.cols_spin.setValue(2)
    window._update_grid()
    window.top_visible_chk.setChecked(False)
    window.bottom_visible_chk.setChecked(True)
    window.font_size_spin.setValue(28)
    window.stroke_width_spin.setValue(5)
    window.uppercase_chk.setChecked(False)

    cell = window.collage.get_cell_at(0, 0)
    assert cell is not None
    cell.caption = "Legend"
    cell.top_caption = "North"
    cell.bottom_caption = "South"

    state = window.get_collage_state()

    new_window = create_window()
    new_window._restore_state(state)

    restored_cell = new_window.collage.get_cell_at(0, 0)
    assert restored_cell is not None
    assert restored_cell.caption == "Legend"
    assert restored_cell.top_caption == "North"
    assert restored_cell.bottom_caption == "South"

    assert new_window.collage.rows == 3
    assert new_window.collage.columns == 2
    assert new_window.rows_spin.value() == 3
    assert new_window.cols_spin.value() == 2
    assert new_window.top_visible_chk.isChecked() is False
    assert new_window.bottom_visible_chk.isChecked() is True
    assert new_window.font_size_spin.value() == 28
    assert new_window.stroke_width_spin.value() == 5
    assert new_window.uppercase_chk.isChecked() is False


def test_mainwindow_autosave_uses_current_state(main_window_factory):
    create_window, autosave_payloads = main_window_factory
    window = create_window()

    window.rows_spin.setValue(4)
    window.cols_spin.setValue(3)
    window._update_grid()

    cell = window.collage.get_cell_at(0, 0)
    assert cell is not None
    cell.caption = "Snapshot"

    autosave_payloads.clear()
    payload = window.autosave.perform_autosave()

    assert autosave_payloads
    assert payload == autosave_payloads[-1]

    assert payload["controls"]["rows"] == 4
    assert payload["controls"]["columns"] == 3
    assert payload["collage"]["rows"] == 4
    assert payload["collage"]["columns"] == 3

    cell_payload = next(
        c for c in payload["collage"]["cells"] if c["row"] == 0 and c["column"] == 0
    )
    assert cell_payload["caption"] == "Snapshot"


def test_add_images_validates_selection_paths(tmp_path, main_window_factory):
    create_window, _ = main_window_factory
    window = create_window()

    valid_path = tmp_path / "photo.png"
    valid_path.write_bytes(b"binary")
    invalid_path = tmp_path / "notes.txt"
    invalid_path.write_text("hello")

    valid, errors = window._validate_selected_images(
        [str(valid_path), str(invalid_path)]
    )

    assert [p for p in valid] == [valid_path.resolve()]
    assert errors
    assert "Unsupported file extension" in errors[0]


def test_add_images_rejects_invalid_urls(monkeypatch, main_window_factory):
    create_window, _ = main_window_factory
    window = create_window()

    monkeypatch.setattr(
        main_module.QFileDialog,
        "getOpenFileNames",
        lambda *_, **__: (["file://example.com/pic.png"], ""),
    )

    warnings: list[tuple[str, str]] = []
    infos: list[tuple[str, str]] = []

    def fake_warning(parent, title, text):
        warnings.append((title, text))
        return main_module.QMessageBox.StandardButton.Ok

    def fake_information(parent, title, text):
        infos.append((title, text))
        return main_module.QMessageBox.StandardButton.Ok

    monkeypatch.setattr(main_module.QMessageBox, "warning", fake_warning)
    monkeypatch.setattr(main_module.QMessageBox, "information", fake_information)

    window._add_images()

    assert warnings, "Expected validation warning for URL-based path"
    warning_title, warning_text = warnings[0]
    assert warning_title == "No Valid Images"
    assert "URLs are not allowed" in warning_text
    assert infos == []

    first_cell = window.collage.get_cell_at(0, 0)
    assert first_cell is not None
    assert getattr(first_cell, "pixmap", None) is None
