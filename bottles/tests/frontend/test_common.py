# ruff: noqa: E402

from types import SimpleNamespace
from unittest.mock import Mock

import pytest


from bottles.backend.utils.manager import ManagerUtils
from bottles.frontend.utils.common import format_runner_name
from bottles.frontend.views.bottle_preferences import PreferencesView


@pytest.mark.parametrize("flatpak", [False, True])
def test_system_source_is_independent_of_packaging(monkeypatch, runner_factory, flatpak):
    from dataclasses import replace
    from bottles.backend.utils.runners import RunnerRegistry

    info = runner_factory("system-wine", "system")
    RunnerRegistry.entries[info.identifier] = replace(info, version="wine-11.0")
    if flatpak:
        monkeypatch.setenv("FLATPAK_ID", "com.usebottles.bottles")
    else:
        monkeypatch.delenv("FLATPAK_ID", raising=False)
    assert format_runner_name(info.identifier) == "System · system-wine (wine-11.0)"


def test_runner_dropdown_uses_display_names_without_changing_ids(monkeypatch, runner_factory):
    runner_factory("system-wine", "system")
    runner_factory("soda-11.0-3")
    monkeypatch.setenv("FLATPAK_ID", "com.usebottles.bottles")
    monkeypatch.setattr(ManagerUtils, "get_languages", lambda: [])
    manager = SimpleNamespace(
        runners_available=["system-wine", "soda-11.0-3"],
        d7vk_available=[],
        dxvk_available=[],
        vkd3d_available=[],
        nvapi_available=[],
        latencyflex_available=[],
    )
    view = SimpleNamespace(manager=manager)
    for name in (
        "runner",
        "d7vk",
        "dxvk",
        "vkd3d",
        "nvapi",
        "latencyflex",
        "language",
        "windows",
    ):
        setattr(view, f"combo_{name}", Mock())
        setattr(view, f"_PreferencesView__set_{name}", Mock())
    for name in (
        "runner",
        "d7vk",
        "dxvk",
        "vkd3d",
        "nvapi",
        "latencyflex",
        "languages",
        "windows",
    ):
        setattr(view, f"str_list_{name}", Mock())

    PreferencesView.update_combo_components(view)

    labels = [call.args[0] for call in view.str_list_runner.append.call_args_list]
    assert labels == ["System · system-wine", "User · soda-11.0-3"]
    assert manager.runners_available[0] == "system-wine"
