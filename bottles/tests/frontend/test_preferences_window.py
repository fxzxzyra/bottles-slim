# ruff: noqa: E402

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bottles.backend.models.result import Result


from bottles.frontend.windows import window as window_module
from bottles.frontend.windows.window import BottlesWindow


class PreferencesDialogStub:
    instances = []

    def __init__(self, window):
        self.window = window
        self.page_name = None
        self.presented_with = None
        self.usage_refreshes = 0
        self.instances.append(self)

    def refresh_component_usage(self):
        self.usage_refreshes += 1

    def set_visible_page_name(self, page):
        self.page_name = page

    def present(self, parent):
        self.presented_with = parent


def test_preferences_dialog_is_reused(monkeypatch):
    PreferencesDialogStub.instances = []
    monkeypatch.setattr(window_module, "PreferencesDialog", PreferencesDialogStub)
    window = SimpleNamespace(_preferences_dialog=None)

    BottlesWindow.show_prefs_view(window)
    BottlesWindow.show_prefs_view(window)

    assert len(PreferencesDialogStub.instances) == 1
    assert window._preferences_dialog.presented_with is window
    assert window._preferences_dialog.usage_refreshes == 2


@pytest.mark.parametrize(
    ("force_offline", "online", "revealed"),
    [
        (True, False, False),
        (False, False, True),
        (False, True, False),
    ],
)
def test_offline_banner_respects_forced_offline_mode(force_offline, online, revealed):
    banner = Mock()
    window = SimpleNamespace(
        settings=SimpleNamespace(
            get_boolean=lambda key: force_offline if key == "force-offline" else False
        ),
        banner_offline=banner,
    )

    BottlesWindow.network_changed_handler.__wrapped__(window, Result(online))

    banner.set_revealed.assert_called_once_with(revealed)


def test_runner_entry_targets_named_preferences_page(monkeypatch):
    PreferencesDialogStub.instances = []
    monkeypatch.setattr(window_module, "PreferencesDialog", PreferencesDialogStub)
    window = SimpleNamespace(_preferences_dialog=None)
    window.show_prefs_view = lambda *args, **kwargs: BottlesWindow.show_prefs_view(window, *args, **kwargs)
    dialog = BottlesWindow.show_prefs_view(window, page="runners")
    assert dialog is window._preferences_dialog
    assert dialog.page_name == "runners"
    assert dialog.presented_with is window
