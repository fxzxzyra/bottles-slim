from threading import Event
from types import SimpleNamespace

import pytest

from bottles.backend.managers import manager as module
from bottles.backend.managers.manager import Manager
from bottles.backend.models.result import Result


@pytest.mark.parametrize("sandbox", [False, True])
def test_creation_uses_exact_directory_and_private_profile(monkeypatch, tmp_path, sandbox):
    root = tmp_path / "Wine"
    root.mkdir()
    root.chmod(0o750)
    captured = {}
    cancel = Event()
    class WineBoot:
        def __init__(self, config):
            captured["config"] = config
        def init(self):
            profile = root / "drive_c/users/hostuser"
            captured["profile"] = profile.is_dir()
            captured["alias"] = (profile.parent / "steamuser").readlink()
            captured["mode"] = root.stat().st_mode & 0o777
            cancel.set()
            return Result(True)
    manager = object.__new__(Manager)
    manager.runners_available = ["soda-11.0"]
    manager.d7vk_available = []
    manager.dxvk_available = []
    manager.vkd3d_available = []
    manager.nvapi_available = []
    manager.latencyflex_available = []
    monkeypatch.setenv("USER", "hostuser")
    monkeypatch.setattr(module.FileUtils, "chattr_f", lambda _path: None)
    monkeypatch.setattr(module.FileUtils, "wait_for_files", lambda *_args, **_kw: False)
    monkeypatch.setattr(module.TemplateManager, "get_env_template", lambda _: None)
    monkeypatch.setattr(module, "Reg", lambda _: None)
    monkeypatch.setattr(module, "RegKeys", lambda _: None)
    monkeypatch.setattr(module, "WineBoot", WineBoot)
    monkeypatch.setattr(module, "WineServer", lambda _: SimpleNamespace(force_kill=lambda: None))
    result = manager.create_bottle(
        name="Office", environment="custom", path=str(root), runner="soda-11.0",
        sandbox=sandbox, cancel_event=cancel,
    )
    assert not result.ok
    assert captured["config"].Path == str(root)
    assert captured["config"].Parameters.sandbox is sandbox
    assert captured["profile"] is True
    assert str(captured["alias"]) == "hostuser"
    assert captured["mode"] == 0o750
    assert root.is_dir()
    assert list(root.iterdir()) == []
    assert not (root / "Office").exists()


def test_creation_rejects_nonempty_target_before_wine(monkeypatch, tmp_path):
    marker = tmp_path / "keep"
    marker.write_text("personal data")
    manager = object.__new__(Manager)
    def forbidden(*args, **kwargs):
        pytest.fail("Wine was initialized for an invalid target")
    monkeypatch.setattr(module, "WineBoot", forbidden)
    monkeypatch.setattr(module, "WineServer", lambda _: SimpleNamespace(force_kill=lambda: None))
    result = manager.create_bottle(name="Office", environment="custom", path=str(tmp_path))
    assert not result.ok
    assert "empty" in result.message
    assert marker.read_text() == "personal data"


def test_creation_rejects_a_profile_link_outside_the_bottle(monkeypatch, tmp_path):
    root = tmp_path / "Wine"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("personal data")
    manager = object.__new__(Manager)
    manager.runners_available = ["soda-11.0"]
    manager.d7vk_available = []
    manager.dxvk_available = []
    manager.vkd3d_available = []
    manager.nvapi_available = []
    manager.latencyflex_available = []
    def unpack(_template, _config):
        users = root / "drive_c/users"
        users.mkdir()
        (users / "steamuser").symlink_to(outside)
        return True
    def forbidden(_config):
        pytest.fail("Wine must not start with an unsafe user profile")
    monkeypatch.setattr(module.FileUtils, "chattr_f", lambda _: None)
    monkeypatch.setattr(module.TemplateManager, "get_env_template", lambda _: {
        "config": {"Installed_Dependencies": [], "Uninstallers": {}},
    })
    monkeypatch.setattr(module.TemplateManager, "unpack_template", unpack)
    monkeypatch.setattr(module, "WineBoot", forbidden)
    monkeypatch.setattr(module, "WineServer", lambda _: SimpleNamespace(force_kill=lambda: None))
    result = manager.create_bottle(name="Office", environment="custom", path=str(root), runner="soda-11.0")
    assert not result.ok
    assert (outside / "keep").read_text() == "personal data"
    assert root.is_dir()
    assert list(root.iterdir()) == []


pytestmark = pytest.mark.usefixtures("local_runner")
