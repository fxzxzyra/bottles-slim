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
