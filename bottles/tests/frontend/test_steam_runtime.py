# ruff: noqa: E402

from types import SimpleNamespace
from unittest.mock import Mock

import gi
import pytest

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Xdp", "1.0")

from gi.repository import Adw

Adw.init()


from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.frontend.views import bottle_preferences
from bottles.frontend.views.bottle_preferences import PreferencesView


@pytest.mark.parametrize(
    ("runtimes", "sensitive"),
    [
        (False, False),
        ({"scout": {}}, True),
    ],
)
@pytest.mark.parametrize("flatpak", [False, True])
def test_steam_runtime_row_explains_availability(monkeypatch, runtimes, sensitive, flatpak):
    if flatpak:
        monkeypatch.setenv("FLATPAK_ID", "com.usebottles.bottles")
    else:
        monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(bottle_preferences.GPUUtils, "is_gpu", lambda _vendor: False)
    monkeypatch.setattr(bottle_preferences.VulkanUtils, "check_support", lambda: False)
    monkeypatch.setattr(bottle_preferences.DisplayUtils, "display_server_type", lambda: "x11")
    monkeypatch.setattr(bottle_preferences, "gamemode_available", False)
    monkeypatch.setattr(
        bottle_preferences.RuntimeManager,
        "get_runtimes",
        lambda _category: runtimes,
    )
    config = BottleConfig()
    manager = Mock()
    manager.update_config.return_value = Result(True, data={"config": config})
    details = SimpleNamespace(window=SimpleNamespace(manager=manager), queue=object())

    view = PreferencesView(details, config)

    view.combo_runner.handler_block_by_func(view._PreferencesView__set_runner)
    view.combo_runner.handler_unblock_by_func(view._PreferencesView__set_runner)

    assert view.row_steam_runtime.get_visible()
    assert view.switch_steam_runtime.get_sensitive() is sensitive
    if not runtimes:
        assert view.row_steam_runtime.get_subtitle() == bottle_preferences._(
            "Steam Runtime was not detected. Install it or grant Bottles access "
            "to Steam files, then restart Bottles."
        )
    else:
        assert view.row_steam_runtime.get_subtitle() == bottle_preferences._(
            "Provide a bundle of extra libraries for more compatibility with Steam "
            "games. Disable it if you run into issues."
        )

    view.switch_steam_runtime.emit("state-set", True)
    if runtimes:
        manager.update_config.assert_called_once_with(
            config=config,
            key="use_steam_runtime",
            value=True,
            scope="Parameters",
        )
    else:
        manager.update_config.assert_not_called()

    # An ordinary application preference must also be wired outside a sandbox.
    # Checking only the Steam row would miss the constructor's early return.
    manager.update_config.reset_mock()
    view.switch_winebridge.emit("state-set", False)
    manager.update_config.assert_called_once_with(
        config=config, key="winebridge", value=False, scope="Parameters",
    )
    assert view.switch_gamemode.get_sensitive() is False
    assert view.combo_dxvk.get_sensitive() is False
