"""HIDRAW changes use Wine's registry and restore the UI after failures."""

from types import SimpleNamespace

import pytest
from gi.repository import Adw

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.utils.hidraw import HidrawDevice
from bottles.frontend.windows import sandbox as module


@pytest.fixture
def hidraw_dialog(monkeypatch):
    identifier = "0x044F/0xB10A"
    monkeypatch.setattr(module, "list_hidraw_devices", lambda: [HidrawDevice(identifier, "Flight & <Stick>")])
    for name in ("supports_input_devices", "supports_usb_devices", "supports_hidraw_devices"):
        monkeypatch.setattr(module.SandboxManager, name, lambda: True)
    callbacks, saves, messages = [], [], []
    config = BottleConfig(Name="Office", Runner="user-custom-name")
    def update_config(**kwargs):
        saves.append(kwargs)
        config.Parameters.hidraw_devices = kwargs["value"]
        return Result(True, {"config": config})
    window = Adw.Window()
    window.manager = SimpleNamespace(update_config=update_config)
    window.show_toast = messages.append
    monkeypatch.setattr(module, "RunAsync", lambda task, callback, **kwargs: callbacks.append((task, callback, kwargs)))
    dialog = module.SandboxDialog(window, config)
    def rows(widget):
        child = widget.get_first_child()
        while child:
            if isinstance(child, Adw.SwitchRow):
                yield child
            yield from rows(child)
            child = child.get_next_sibling()
    row = next(rows(dialog.group_hidraw))
    yield dialog, row, callbacks, saves, messages, config
    dialog.destroy()
    window.destroy()


def test_hidraw_selection_saves_only_after_wine_registry_succeeds(hidraw_dialog):
    dialog, row, callbacks, saves, messages, config = hidraw_dialog
    assert not row.get_use_markup()
    assert row.get_title() == "Flight & <Stick>"
    row.set_active(True)
    assert not dialog.group_hidraw.get_sensitive()
    assert saves == []
    task, callback, kwargs = callbacks.pop()
    assert task is module.configure_hidraw
    assert kwargs == {"config": config, "identifiers": ["0x044F/0xB10A"]}
    callback(Result(True), None)
    assert config.Parameters.hidraw_devices == ["0x044F/0xB10A"]
    assert dialog.group_hidraw.get_sensitive()
    assert row.get_active()
    assert messages == []
    row.set_active(False)
    _task, callback, kwargs = callbacks.pop()
    assert kwargs["identifiers"] == []
    callback(Result(True), None)
    assert config.Parameters.hidraw_devices == []
    assert dialog.group_hidraw.get_sensitive()


@pytest.mark.parametrize("result,error", [(Result(False, message="Registry failed"), None), (None, RuntimeError("Registry failed"))])
def test_hidraw_failure_restores_switch_without_persisting_selection(hidraw_dialog, result, error):
    dialog, row, callbacks, saves, messages, config = hidraw_dialog
    row.set_active(True)
    _task, callback, _kwargs = callbacks.pop()
    callback(result, error)
    assert saves == []
    assert config.Parameters.hidraw_devices == []
    assert not row.get_active()
    assert dialog.group_hidraw.get_sensitive()
    assert messages == ["Registry failed"]
    assert callbacks == []
