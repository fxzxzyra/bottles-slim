"""Real application template and adaptive header without booting Wine/networking."""

from types import SimpleNamespace

import pytest
from gi.repository import Adw, Gtk

from bottles.backend.state import SignalManager
from bottles.frontend.windows import window as module


@pytest.fixture
def shell(monkeypatch):
    monkeypatch.setattr(SignalManager, "_SIGNALS", {})
    monkeypatch.setattr(module, "DataManager", lambda: SimpleNamespace(get=lambda *_args: None))
    # Startup loads runners, catalogs and application pages. The shell and its
    # navigation/breakpoint code remain real; no Wine or network is required.
    monkeypatch.setattr(module.BottlesWindow, "_BottlesWindow__on_start", lambda _self: None)
    window = module.BottlesWindow(arg_bottle=None)
    yield window
    window.destroy()


def test_application_navigation_and_back_button(shell):
    assert isinstance(shell.main_navigation, Adw.NavigationView)
    details = Adw.NavigationPage.new(Gtk.Box(), "Details")
    details.set_tag("details")
    shell.details_page = details
    importer = Adw.NavigationPage.new(Gtk.Box(), "Import")
    importer.set_tag("importer")
    shell.importer_page = importer
    shell.main_navigation.add(details)
    shell.main_navigation.add(importer)
    shell.show_importer_view()
    shell.show_importer_view()
    assert shell.main_navigation.get_visible_page() is importer
    shell.go_back()
    assert shell.main_navigation.get_visible_page() is shell.home_page


def test_header_adapts_and_restores_at_breakpoint(shell, iterate_until):
    shell.set_default_size(880, 640)
    shell.present()
    iterate_until(lambda: shell.get_width() > 550)
    assert shell.header_title.get_visible_child_name() == "switcher"
    assert not shell.view_switcher_bar.get_reveal()
    shell.set_default_size(500, 640)
    iterate_until(lambda: shell.header_title.get_visible_child_name() == "title")
    assert shell.view_switcher_bar.get_reveal()
    shell.title("Bottles", "Offline")
    assert shell.window_title.get_subtitle() == "Offline"
    shell.lock_ui(True)
    assert not shell.view_switcher_bar.get_sensitive()
    shell.lock_ui(False)
    shell.set_default_size(880, 640)
    iterate_until(lambda: shell.header_title.get_visible_child_name() == "switcher")
    assert not shell.view_switcher_bar.get_reveal()
