from types import SimpleNamespace
from unittest.mock import Mock

from bottles.frontend.views.preferences import PreferencesDialog
from bottles.frontend.widgets import component as module
from bottles.frontend.widgets.component import ComponentEntry
from bottles.frontend.windows.window import BottlesWindow


def test_reopening_preferences_updates_component_usage():
    active = {"dxvk-old"}
    window = SimpleNamespace(manager=SimpleNamespace(
        component_manager=SimpleNamespace(is_in_use=lambda _kind, name: name in active),
        utils_conn=SimpleNamespace(status=True),
    ))
    entries = [ComponentEntry(window, [name, {"Installed": True}], "dxvk")
               for name in ("dxvk-old", "dxvk-new")]
    preferences = SimpleNamespace(_PreferencesDialog__registry=entries, present=Mock())
    preferences.refresh_component_usage = lambda: PreferencesDialog.refresh_component_usage(preferences)
    window._preferences_dialog = preferences
    assert not entries[0].btn_remove.get_visible()
    assert entries[1].btn_remove.get_visible()
    active.clear()
    active.add("dxvk-new")
    BottlesWindow.show_prefs_view(window)
    assert entries[0].btn_remove.get_visible()
    assert not entries[1].btn_remove.get_visible()


def test_usage_refresh_does_not_offer_removal_during_uninstall(monkeypatch):
    manager = SimpleNamespace(is_in_use=lambda *_args: False, uninstall=lambda **_kwargs: None)
    window = SimpleNamespace(manager=SimpleNamespace(component_manager=manager, utils_conn=SimpleNamespace(status=True)))
    entry = ComponentEntry(window, ["dxvk", {"Installed": True}], "dxvk")
    pending = []
    monkeypatch.setattr(module, "RunAsync", lambda **kwargs: pending.append(kwargs))
    assert entry.btn_remove.get_visible()
    entry.uninstall(None)
    entry.refresh_usage()
    assert len(pending) == 1
    assert not entry.btn_remove.get_visible()
