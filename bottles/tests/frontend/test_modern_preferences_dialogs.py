"""Adaptive dialog lifecycle and actual DLL-entry signals on built templates."""

from types import SimpleNamespace
from unittest.mock import Mock

from gi.repository import Adw, Gio

from bottles.backend.models.config import BottleConfig
from bottles.frontend.params import APP_ID
from bottles.frontend.views import preferences
from bottles.frontend.windows.dlloverrides import DLLOverridesDialog


def test_preferences_dialog_can_close_and_present_again(monkeypatch, iterate_until):
    jobs = []
    monkeypatch.setattr(preferences, "RunAsync", lambda *args, **kwargs: jobs.append((args, kwargs)))
    parent = Adw.Window()
    parent.settings = Gio.Settings.new(APP_ID)
    parent.manager = SimpleNamespace(
        data_mgr=SimpleNamespace(get=lambda *_args: None),
        utils_conn=SimpleNamespace(status=False),
        steam_manager=SimpleNamespace(is_steam_supported=False),
        get_cache_details=lambda: {},
    )
    dialog = preferences.PreferencesDialog(parent)
    parent.present()
    try:
        assert isinstance(dialog, Adw.PreferencesDialog)
        for _open in range(2):
            dialog.present(parent)
            iterate_until(lambda: parent.get_visible_dialog() is dialog)
            assert dialog.get_content_width() == 750
            dialog.close()
            iterate_until(lambda: parent.get_visible_dialog() is None)
    finally:
        dialog.force_close()
        parent.destroy()


def test_dll_dialog_validates_and_saves_using_entry_signals(iterate_until):
    parent = Adw.Window()
    parent.manager = SimpleNamespace(update_config=Mock())
    config = BottleConfig()
    dialog = DLLOverridesDialog(parent, config)
    parent.present()
    try:
        dialog.present(parent)
        assert isinstance(dialog, Adw.PreferencesDialog)
        dialog.entry_row.set_text("dxgi")
        assert dialog.entry_row.has_css_class("error")
        assert not dialog.entry_row.get_show_apply_button()
        dialog.entry_row.emit("apply")
        parent.manager.update_config.assert_not_called()
        dialog.entry_row.set_text("custom")
        assert not dialog.entry_row.has_css_class("error")
        assert dialog.entry_row.get_show_apply_button()
        dialog.entry_row.emit("apply")
        parent.manager.update_config.assert_called_once_with(
            config=config, key="custom", value="n,b", scope="DLL_Overrides",
        )
        iterate_until(lambda: dialog.group_overrides.get_description() == "")
        assert dialog.entry_row.get_text() == ""
    finally:
        dialog.force_close()
        parent.destroy()
