# ruff: noqa: E402

import time
from types import SimpleNamespace
from unittest.mock import Mock

import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

Adw.init()

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.frontend.windows.display import DisplayDialog, RegKeys


@pytest.mark.parametrize(("mode", "success"), [(0, True), (1, True), (2, True), (1, False)])
def test_display_saves_dpi_scaling_only_after_the_registry_update(monkeypatch, mode, success):
    config = BottleConfig()
    window = Adw.Window()
    window.show_toast = Mock()

    def save(**kwargs):
        assert kwargs["key"] == "Parameters"
        assert kwargs["value"].dpi_scaling == ("application" if mode == 1 else "system")
        config.Parameters = kwargs["value"]
        return Result(True, {"config": config})

    window.manager = SimpleNamespace(update_config=Mock(side_effect=save))
    queue = SimpleNamespace(add_task=Mock(), end_task=Mock())
    spinner = Gtk.Spinner()
    button = Gtk.Button()
    monkeypatch.setattr(RegKeys, "get_dpi_scaling", lambda self: Result(True, "default"))
    dialog = DisplayDialog(window, config, None, queue, button, spinner)
    context = GLib.MainContext.default()
    deadline = time.monotonic() + 5
    while dialog.dpi_scaling is None and time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)
    assert dialog.dpi_scaling == "default"
    registry = Mock(return_value=Result(success, message="Registry failed"))
    monkeypatch.setattr(RegKeys, "set_dpi_scaling", registry)
    dialog.combo_dpi_scaling.set_selected(mode)
    dialog.btn_save.emit("clicked")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if mode == 0 or queue.end_task.called:
            break
        time.sleep(0.01)
    if mode == 0:
        registry.assert_not_called()
        window.manager.update_config.assert_not_called()
    else:
        expected = "application" if mode == 1 else "system"
        registry.assert_called_once_with(mode=expected)
        queue.end_task.assert_called_once()
        assert button.get_sensitive()
        assert not spinner.get_spinning()
        if success:
            assert config.Parameters.dpi_scaling == expected
            window.manager.update_config.assert_called_once()
        else:
            assert config.Parameters.dpi_scaling == "default"
            window.manager.update_config.assert_not_called()
            assert window.show_toast.call_count == 2
    dialog.destroy()
    window.destroy()


@pytest.mark.parametrize(("mode", "success"), [("application", True), ("system", True), ("default", False)])
def test_display_reads_existing_manual_dpi_settings(monkeypatch, mode, success):
    config = BottleConfig()
    window = Adw.Window()
    window.manager = SimpleNamespace(update_config=Mock())
    window.show_toast = Mock()
    completed = []

    def read(self):
        completed.append(True)
        return Result(success, mode)

    monkeypatch.setattr(RegKeys, "get_dpi_scaling", read)
    registry = Mock()
    monkeypatch.setattr(RegKeys, "set_dpi_scaling", registry)
    dialog = DisplayDialog(window, config, None, SimpleNamespace(), Gtk.Button(), Gtk.Spinner())
    context = GLib.MainContext.default()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if completed and (dialog.dpi_scaling is not None or window.show_toast.called):
            break
        time.sleep(0.01)
    assert dialog.combo_dpi_scaling.get_sensitive() is success
    if success:
        assert dialog.combo_dpi_scaling.get_selected() == (1 if mode == "application" else 2)
    dialog.btn_save.emit("clicked")
    while context.pending():
        context.iteration(False)
    registry.assert_not_called()
    window.manager.update_config.assert_not_called()
    dialog.destroy()
    window.destroy()


def _drain_until(condition):
    context = GLib.MainContext.default()
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)
    assert condition(), "Display settings operation did not complete"


@pytest.mark.parametrize("failure", [None, "registry", "exception", "config", "config-exception"])
def test_display_preserves_failed_settings_and_completes_other_changes(monkeypatch, failure):
    config = BottleConfig()
    previous_dpi = config.Parameters.custom_dpi
    previous_renderer = config.Parameters.renderer
    window = Adw.Window()
    window.show_toast = Mock()
    saves = []

    def save(**kwargs):
        config.Parameters = kwargs["value"]
        saves.append(config.Parameters.copy())
        if failure == "config-exception":
            raise OSError("Could not write bottle.yml")
        return Result(not (failure == "config" and len(saves) == 1), {"config": config})

    window.manager = SimpleNamespace(update_config=Mock(side_effect=save))
    queue = SimpleNamespace(add_task=Mock(), end_task=Mock())
    spinner, button = Gtk.Spinner(), Gtk.Button()
    order = []

    def set_dpi(self, value):
        order.append(("dpi", value))
        if failure == "exception":
            raise OSError("Cannot update registry")
        return Result(failure != "registry", message="Cannot update DPI")

    def set_renderer(self, value):
        order.append(("renderer", value))
        return Result(True)

    monkeypatch.setattr(RegKeys, "get_dpi_scaling", lambda self: Result(True, "default"))
    monkeypatch.setattr(RegKeys, "set_dpi", set_dpi)
    monkeypatch.setattr(RegKeys, "set_renderer", set_renderer)
    dialog = DisplayDialog(window, config, None, queue, button, spinner)
    try:
        _drain_until(lambda: dialog.dpi_scaling is not None)
        dialog.spin_dpi.set_value(previous_dpi + 24)
        renderer = "vulkan" if previous_renderer != "vulkan" else "gdi"
        dialog.combo_renderer.set_selected(2 if renderer == "vulkan" else 1)
        dialog.btn_save.emit("clicked")
        assert not button.get_sensitive()
        _drain_until(lambda: queue.end_task.called)
        assert order == [("dpi", previous_dpi + 24), ("renderer", renderer)]
        assert config.Parameters.custom_dpi == (previous_dpi + 24 if failure is None else previous_dpi)
        assert config.Parameters.renderer == (previous_renderer if failure in ("config", "config-exception") else renderer)
        # Registry failures must not leak into the one combined configuration write.
        assert len(saves) == 1
        if failure not in ("config", "config-exception"):
            assert saves[0].custom_dpi == config.Parameters.custom_dpi
        assert window.show_toast.call_count == 2
        queue.add_task.assert_called_once()
        queue.end_task.assert_called_once()
        assert button.get_sensitive()
        assert not spinner.get_spinning()
    finally:
        dialog.destroy()
        window.destroy()


@pytest.mark.parametrize("success", [False, True])
def test_virtual_desktop_and_resolution_are_applied_and_saved_together(monkeypatch, success):
    config = BottleConfig()
    config.Parameters.virtual_desktop = False
    config.Parameters.virtual_desktop_res = "800x600"
    original = config.Parameters.copy()
    window = Adw.Window()
    window.show_toast = Mock()

    def save(**kwargs):
        config.Parameters = kwargs["value"]
        return Result(True, {"config": config})

    window.manager = SimpleNamespace(update_config=Mock(side_effect=save))
    queue = SimpleNamespace(add_task=Mock(), end_task=Mock())
    monkeypatch.setattr(RegKeys, "get_dpi_scaling", lambda self: Result(True, "default"))
    registry = Mock(return_value=Result(success))
    monkeypatch.setattr(RegKeys, "toggle_virtual_desktop", registry)
    dialog = DisplayDialog(window, config, None, queue, Gtk.Button(), Gtk.Spinner())
    try:
        _drain_until(lambda: dialog.dpi_scaling is not None)
        dialog.expander_virtual_desktop.set_enable_expansion(True)
        dialog.spin_width.set_value(1920)
        dialog.spin_height.set_value(1080)
        dialog.btn_save.emit("clicked")
        _drain_until(lambda: queue.end_task.called)
        registry.assert_called_once_with(state=True, resolution="1920x1080")
        assert config.Parameters.virtual_desktop is success
        assert config.Parameters.virtual_desktop_res == ("1920x1080" if success else original.virtual_desktop_res)
        assert window.manager.update_config.call_count == int(success)
    finally:
        dialog.destroy()
        window.destroy()
