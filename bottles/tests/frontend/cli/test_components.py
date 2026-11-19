"""GUI and CLI component changes use the same backend operation."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from gi.repository import Gio

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result

with patch.object(Gio.Settings, "new", return_value=object()):
    from bottles.frontend.cli import cli as module


@pytest.mark.parametrize("component,flag", [
    ("d7vk", "d7vk"), ("dxvk", "dxvk"), ("vkd3d", "vkd3d"),
    ("nvapi", "dxvk_nvapi"), ("latencyflex", "latencyflex"),
])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("params", [False, True])
def test_cli_component_options_and_flags_use_the_shared_operation(monkeypatch, component, flag, enabled, params):
    config = BottleConfig(Name="Work")
    manager = SimpleNamespace(
        local_bottles={config.Id: config}, check_bottles=Mock(),
        set_dll_component=Mock(return_value=Result(True)),
        update_config=Mock(side_effect=AssertionError("Component persistence belongs to the backend operation")),
    )
    monkeypatch.setattr(module, "Manager", lambda **_kwargs: manager)
    args = dict(bottle=config.Id, params=None, env_var=None, win=None, runner=None,
                d7vk=None, dxvk=None, vkd3d=None, nvapi=None, latencyflex=None)
    if params:
        args["params"] = f"{flag}:{str(enabled).lower()}"
    else:
        args[component] = "selected-version" if enabled else "disabled"
    cli = module.CLI.__new__(module.CLI)
    cli.args = SimpleNamespace(**args)
    cli.edit_bottle()
    manager.set_dll_component.assert_called_once_with(
        config, component, enabled, "selected-version" if enabled and not params else None,
    )
    manager.update_config.assert_not_called()


def test_cli_component_failure_stops_before_later_requested_changes(monkeypatch):
    config = BottleConfig()
    manager = SimpleNamespace(
        local_bottles={config.Id: config}, check_bottles=Mock(),
        set_dll_component=Mock(return_value=Result(False, message="Cannot install")),
        update_config=Mock(),
    )
    monkeypatch.setattr(module, "Manager", lambda **_kwargs: manager)
    cli = module.CLI.__new__(module.CLI)
    cli.args = SimpleNamespace(
        bottle=config.Id, params=None, env_var=None, win=None, runner=None,
        d7vk=None, dxvk="new", vkd3d="later", nvapi=None, latencyflex=None,
    )
    with pytest.raises(SystemExit) as error:
        cli.edit_bottle()
    assert error.value.code == 1
    manager.set_dll_component.assert_called_once_with(config, "dxvk", True, "new")
    manager.update_config.assert_not_called()
