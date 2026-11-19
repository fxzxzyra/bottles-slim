"""Registry import serializes Unicode values and protects temporary path boundaries."""

from types import SimpleNamespace
import shlex

import pytest

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.utils.hidraw import hidraw_registry_bundle
from bottles.backend.wine import reg


@pytest.mark.parametrize("success", [True, False])
def test_registry_import_uses_unicode_private_file_and_exact_arguments(tmp_path, monkeypatch, success):
    folder = tmp_path / "User's registry 文件"
    folder.mkdir(mode=0o700)
    path = folder / "settings.reg"
    monkeypatch.setattr(reg.ManagerUtils, "get_temp_path", lambda _name, _config: str(path))
    monkeypatch.setattr(reg, "WineDbg", lambda _config: SimpleNamespace(wait_for_process=lambda _name: None))
    captured = {}
    result = Result(success)
    registry = reg.Reg.__new__(reg.Reg)
    registry.config = BottleConfig(Name="Office")
    def launch(args, **kwargs):
        captured["args"] = args
        captured["content"] = path.read_text(encoding="utf-16")
        captured["bytes"] = path.read_bytes()
        captured["mode"] = path.stat().st_mode & 0o777
        return result
    registry.launch = launch
    bundle = hidraw_registry_bundle(["0x044F/0xB10A"])
    bundle[r"HKEY_CURRENT_USER\Software\Example"] = [{"value": "Title", "data": "中文标题"}]
    assert registry.import_bundle(bundle) is result
    assert shlex.split(captured["args"]) == ["import", str(path)]
    assert captured["bytes"].startswith(b"\xff\xfe")
    assert captured["content"].startswith("Windows Registry Editor Version 5.00\n")
    assert '"EnableHidraw"=hex(7):' in captured["content"]
    assert '"Title"="中文标题"' in captured["content"]
    assert captured["mode"] == 0o600
    assert not path.exists()


def test_bulk_registry_import_retains_nonadjacent_keys_and_native_types():
    registry = reg.Reg.__new__(reg.Reg)
    captured = []
    success = Result(True)
    registry.import_bundle = lambda bundle: captured.append(bundle) or success
    items = [
        reg.RegItem("KeyA", "First", "", "Font"),
        reg.RegItem("KeyB", "Enabled", "dword", "00000001"),
        reg.RegItem("KeyA", "Second", "", "Other Font"),
    ]
    assert registry.bulk_add(items) is success
    assert captured == [{
        "KeyA": [{"value": "First", "data": "Font"}, {"value": "Second", "data": "Other Font"}],
        "KeyB": [{"value": "Enabled", "data": "00000001", "key_type": "dword"}],
    }]


@pytest.mark.parametrize("operation", ["add", "remove"])
@pytest.mark.parametrize("success", [False, True])
def test_registry_edits_return_the_actual_command_result(monkeypatch, operation, success):
    monkeypatch.setattr(reg, "WineDbg", lambda _config: SimpleNamespace(wait_for_process=lambda _name: None))
    registry = reg.Reg.__new__(reg.Reg)
    registry.config = BottleConfig(Name="Office")
    result = Result(success, message="Command failed" if not success else "")
    registry.launch = lambda *_args, **_kwargs: result
    kwargs = {"key": r"HKCU\Software\Example", "value": "Enabled"}
    if operation == "add":
        kwargs["data"] = "Y"
    assert getattr(registry, operation)(**kwargs) is result


@pytest.mark.parametrize("failure", [None, "desktop", "resolution", "wineboot"])
def test_virtual_desktop_stops_at_first_failure(monkeypatch, failure):
    from unittest.mock import Mock
    from bottles.backend.wine import regkeys

    keys = regkeys.RegKeys(BottleConfig())
    keys.reg = SimpleNamespace(add=Mock(side_effect=[
        Result(failure != "desktop"), Result(failure != "resolution"),
    ]))
    boot = Mock(return_value=Result(failure != "wineboot"))
    monkeypatch.setattr(regkeys, "WineBoot", lambda _config: SimpleNamespace(update=boot))

    result = keys.toggle_virtual_desktop(True, "1920x1080")

    assert result.ok is (failure is None)
    assert keys.reg.add.call_count == (1 if failure == "desktop" else 2)
    assert boot.call_count == (0 if failure in ("desktop", "resolution") else 1)
    if failure != "desktop":
        assert keys.reg.add.call_args.kwargs["data"] == "1920x1080"


@pytest.mark.parametrize("method,kwargs", [
    ("set_renderer", {"value": "vulkan"}),
    ("set_dpi", {"value": 144}),
    ("set_mouse_warp", {"state": 1}),
])
@pytest.mark.parametrize("success", [False, True])
def test_display_registry_wrappers_propagate_failures(method, kwargs, success):
    from bottles.backend.wine.regkeys import RegKeys

    keys = RegKeys(BottleConfig())
    result = Result(success)
    keys.reg = SimpleNamespace(add=lambda **_kwargs: result)
    assert getattr(keys, method)(**kwargs) is result


@pytest.mark.parametrize("success", [False, True])
def test_virtual_desktop_disable_does_not_restart_after_registry_failure(monkeypatch, success):
    from unittest.mock import Mock
    from bottles.backend.wine import regkeys

    keys = regkeys.RegKeys(BottleConfig())
    keys.reg = SimpleNamespace(remove=Mock(return_value=Result(success)))
    boot = Mock(return_value=Result(True))
    monkeypatch.setattr(regkeys, "WineBoot", lambda _config: SimpleNamespace(update=boot))
    assert keys.toggle_virtual_desktop(False).ok is success
    keys.reg.remove.assert_called_once_with(
        key=r"HKEY_CURRENT_USER\Software\Wine\Explorer", value="Desktop",
    )
    assert boot.call_count == int(success)
