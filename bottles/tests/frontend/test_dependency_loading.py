"""Slow manifest and cache reads must leave the GTK main loop responsive."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from gi.repository import GLib, Gtk

from bottles.backend.models.config import BottleConfig
from bottles.frontend.views import bottle_dependencies
from bottles.frontend.widgets import dependency as dependency_widget


def _wait_until(predicate):
    deadline = time.monotonic() + 3
    context = GLib.MainContext.default()
    while not predicate() and time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.001)
    assert predicate()


def test_dependency_cache_read_runs_outside_main_loop(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    threads = []

    def lookup(*_args, **_kwargs):
        threads.append(threading.current_thread())
        started.set()
        assert release.wait(3)
        return True

    window = Gtk.Window()
    config = BottleConfig(Installed_Dependencies=["already-installed"])
    window.manager = SimpleNamespace(
        utils_conn=SimpleNamespace(status=False),
        supported_dependencies={"font": {
            "Description": "Font", "Category": "Fonts", "Arch": "win64_win32",
        }},
        dependency_manager=SimpleNamespace(is_dependency_cached=lookup),
    )
    window.show_toast = Mock()
    window.page_details = SimpleNamespace(queue=None)
    monkeypatch.setattr(bottle_dependencies.EventManager, "wait", lambda *_: None)
    view = bottle_dependencies.DependenciesView(
        SimpleNamespace(window=window, queue=None), config,
    )
    window.set_child(view)
    try:
        view.update(config=config)
        _wait_until(started.is_set)
        responsive = []
        GLib.idle_add(lambda: responsive.append(True))
        _wait_until(lambda: bool(responsive))
        assert not release.is_set()
        assert view.stack.get_visible_child_name() == "page_loading"
        release.set()
        _wait_until(lambda: view.stack.get_visible_child_name() == "page_deps")
        row = view.list_dependencies.get_first_child()
        assert row.get_title() == "font"
        assert row.btn_install.get_visible()
        assert len(threads) == 1
        assert threads[0] is not threading.main_thread()
        window.show_toast.assert_not_called()
    finally:
        release.set()
        window.destroy()


@pytest.mark.parametrize("plain", [True, False])
@pytest.mark.parametrize("success", [True, False])
def test_manifest_actions_fetch_in_worker_and_restore_controls(monkeypatch, plain, success):
    started = threading.Event()
    release = threading.Event()
    completed = []
    threads = []

    def get_dependency(name, plain):
        assert name == "font"
        threads.append(threading.current_thread())
        started.set()
        assert release.wait(3)
        if not success:
            raise OSError("network unavailable")
        return "manifest contents" if plain else {"License_url": "https://example.org/license"}

    window = SimpleNamespace(
        manager=SimpleNamespace(
            utils_conn=SimpleNamespace(status=True),
            dependency_manager=SimpleNamespace(get_dependency=get_dependency),
        ),
        page_details=SimpleNamespace(queue=None), show_toast=Mock(),
    )
    monkeypatch.setattr(dependency_widget, "SourceDialog", lambda **kwargs: SimpleNamespace(
        present=lambda: completed.append(kwargs["message"]),
    ))
    monkeypatch.setattr(dependency_widget.webbrowser, "open", completed.append)
    row = dependency_widget.DependencyEntry(window, BottleConfig(), ("font", {
        "Description": "Font", "Category": "Fonts", "Arch": "win64_win32",
    }))
    button = row.btn_manifest if plain else row.btn_license
    try:
        button.emit("clicked")
        _wait_until(started.is_set)
        assert not button.get_sensitive()
        assert row.spinner.get_visible()
        responsive = []
        GLib.idle_add(lambda: responsive.append(True))
        _wait_until(lambda: bool(responsive))
        assert completed == []
        release.set()
        _wait_until(lambda: button.get_sensitive())
        assert button.get_sensitive()
        assert not row.spinner.get_visible()
        assert threads[0] is not threading.main_thread()
        if success:
            assert completed == (["manifest contents"] if plain else ["https://example.org/license"])
            window.show_toast.assert_not_called()
        else:
            assert completed == []
            window.show_toast.assert_called_once()
    finally:
        release.set()
