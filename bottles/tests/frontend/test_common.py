# ruff: noqa: E402

from types import SimpleNamespace

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
    from bottles.backend.models.config import BottleConfig
    from bottles.frontend.views import bottle_preferences

    monkeypatch.setattr(bottle_preferences.GPUUtils, "is_gpu", lambda _vendor: False)
    monkeypatch.setattr(bottle_preferences.VulkanUtils, "check_support", lambda: False)
    monkeypatch.setattr(bottle_preferences.DisplayUtils, "display_server_type", lambda: "x11")
    monkeypatch.setattr(bottle_preferences.RuntimeManager, "get_runtimes", lambda _category: False)
    details = SimpleNamespace(window=SimpleNamespace(manager=manager), queue=object())
    view = PreferencesView(details, BottleConfig(Runner="system-wine"))
    view.update_combo_components()

    labels = [view.str_list_runner.get_string(index) for index in range(view.str_list_runner.get_n_items())]
    assert labels == ["System · system-wine", "User · soda-11.0-3"]
    assert view._runner_ids == ["system-wine", "soda-11.0-3"]
    assert manager.runners_available[0] == "system-wine"
