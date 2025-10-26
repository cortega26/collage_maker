import builtins
import logging
import os
from pathlib import Path

import pytest

from src import config
from src.managers.autosave import AutosaveError, AutosaveManager, autosave_metrics


class DummyTimer:
    """Stub QTimer used for testing."""

    def __init__(self):
        self.timeout = type("T", (), {"connect": lambda *a, **k: None})()

    def start(self, *_):
        pass


def setup_manager(tmp_path):
    autosave_metrics.counters.clear()
    autosave_metrics.durations.clear()
    manager = AutosaveManager(parent=None, save_callback=lambda: {"foo": "bar"}, timer=DummyTimer())
    manager.path = str(tmp_path)
    os.makedirs(manager.path, exist_ok=True)
    return manager


def test_autosave_retries_and_logs(tmp_path, caplog, monkeypatch):
    manager = setup_manager(tmp_path)

    orig_open = builtins.open
    attempts = {"count": 0}

    def fake_open(*args, **kwargs):
        if attempts["count"] < 2:
            attempts["count"] += 1
            raise OSError("boom")
        return orig_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    caplog.set_level(logging.INFO)
    manager.perform_autosave()

    assert attempts["count"] == 2
    assert autosave_metrics.counters["success"] == 1
    assert any("cid" in r.__dict__ for r in caplog.records)


def test_autosave_failure_raises(tmp_path, monkeypatch):
    manager = setup_manager(tmp_path)

    def always_fail(*_, **__):
        raise OSError("disk full")

    monkeypatch.setattr(builtins, "open", always_fail)

    with pytest.raises(AutosaveError):
        manager.perform_autosave()

    assert autosave_metrics.counters["failure"] == 1


def test_cleanup_logs_warning(tmp_path, caplog, monkeypatch):
    manager = setup_manager(tmp_path)
    for i in range(config.MAX_AUTOSAVE_FILES + 1):
        Path(manager.path, f"collage_autosave_{i}.json").write_text("{}")

    def fail_remove(_):
        raise OSError("nope")

    monkeypatch.setattr(os, "remove", fail_remove)

    caplog.set_level(logging.WARNING)
    manager._cleanup_old()

    assert any("cleanup failed" in r.message for r in caplog.records)

