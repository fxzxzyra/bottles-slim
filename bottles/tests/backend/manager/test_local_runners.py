import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bottles.backend.globals import Paths
from bottles.backend.managers.data import UserDataKeys
from bottles.backend.managers.manager import Manager
from bottles.backend.models.config import BottleConfig
from bottles.backend.utils import runners
from bottles.backend.utils.manager import ManagerUtils
from bottles.backend.utils.runners import RunnerRegistry, SYSTEM_WINE
from bottles.backend.wine.winecommand import WineCommand


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "user_runners", str(tmp_path / "managed"))
    monkeypatch.setattr(Paths, "system_runners", ())
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(RunnerRegistry, "entries", {})
    monkeypatch.setattr(RunnerRegistry, "system", lambda: None)
    data = {}
    manager = object.__new__(Manager)
    manager.data_mgr = SimpleNamespace(get=data.get, set=data.__setitem__)
    manager.steam_manager = SimpleNamespace(list_compatibility_tools=lambda: {})
    manager.local_bottles = {}
    return manager


def test_system_runner_is_primary_and_discovery_is_read_only(
    manager, runner_factory, monkeypatch
):
    user = runner_factory("soda-11.0")
    system = runner_factory(SYSTEM_WINE, "system")
    marker = Path(user.root) / "lib/wine/x86_64-windows/winemenubuilder.exe"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"keep")
    manager.data_mgr.set(UserDataKeys.UserRunners, {user.identifier: user.root})
    monkeypatch.setattr(RunnerRegistry, "system", lambda: system)

    assert manager.check_runners()
    assert manager.runners_available == [SYSTEM_WINE, user.identifier]
    assert manager.get_default_runner() == SYSTEM_WINE
    assert marker.read_bytes() == b"keep"
    assert not marker.with_suffix(".exe.lock").exists()


def test_missing_runner_has_no_download_fallback(manager):
    # No component manager or connection object is provided: discovery must
    # have no way to consult a remote catalog or install a runner.
    assert manager.check_runners() is False
    assert manager.get_default_runner() == ""


def test_import_and_forget_preserve_files_and_identifier(manager, runner_factory):
    info = runner_factory("custom-wine")
    RunnerRegistry.entries = {}

    result = manager.add_user_runner(info.root)
    assert result.ok
    identifier = result.data["runner"]
    assert manager.check_runners()
    assert manager.runners_available == [identifier]
    assert ManagerUtils.get_runner_path(identifier) == info.root
    assert not manager.add_user_runner(info.root).ok
    manager.local_bottles = {"test": BottleConfig(Runner=identifier)}
    assert not manager.remove_user_runner(identifier).ok
    manager.local_bottles = {}
    assert manager.remove_user_runner(identifier).ok
    assert manager.runners_available == []
    assert Path(info.wine).is_file()
    assert Path(info.wineserver).is_file()


def test_local_import_requires_matching_server(manager, runner_factory):
    info = runner_factory("incomplete")
    Path(info.wineserver).unlink()
    RunnerRegistry.entries = {}
    assert not manager.add_user_runner(info.root).ok
    assert not manager.data_mgr.get(UserDataKeys.UserRunners)


def test_discover_legacy_and_external_runners(manager, runner_factory, monkeypatch):
    managed = runner_factory("managed")
    external = runner_factory("external")
    monkeypatch.setattr(Paths, "user_runners", str(Path(managed.root).parent))
    # Place the external runner outside the managed directory.
    monkeypatch.setattr(
        manager.steam_manager, "list_compatibility_tools",
        lambda: {"from-steam": external.root},
    )
    assert manager.check_runners()
    assert ManagerUtils.get_runner_path("managed") == managed.root
    assert ManagerUtils.get_runner_path("from-steam") == external.root
    assert not manager.remove_user_runner("from-steam").ok
    assert Path(external.wine).exists()


def test_system_version_is_metadata_and_path_does_not_follow_later_path_changes(
    runner_factory, monkeypatch
):
    system = runner_factory(SYSTEM_WINE, "system")
    monkeypatch.setattr(runners.shutil, "which", lambda _: system.wine)
    monkeypatch.setattr(
        runners.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="wine-11.0\n"),
    )
    first = RunnerRegistry.system()
    monkeypatch.setattr(
        runners.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="wine-11.1\n"),
    )
    second = RunnerRegistry.system()
    assert first.identifier == second.identifier == SYSTEM_WINE
    assert first.version != second.version
    RunnerRegistry.entries = {SYSTEM_WINE: second}
    monkeypatch.setattr(runners.shutil, "which", lambda _: "/wrong/wine")
    command = object.__new__(WineCommand)
    command.config = BottleConfig(Runner=SYSTEM_WINE)
    assert command._get_runner_info() == (system.wine, "")


@pytest.mark.parametrize("failure", [OSError("unusable"), subprocess.TimeoutExpired("wine", 5)])
def test_system_probe_failures_leave_runner_unavailable(runner_factory, monkeypatch, failure):
    info = runner_factory(SYSTEM_WINE, "system")
    monkeypatch.setattr(runners.shutil, "which", lambda _: info.wine)

    def fail(*a, **kw):
        raise failure

    monkeypatch.setattr(runners.subprocess, "run", fail)
    assert RunnerRegistry.system() is None


def test_missing_selected_runner_does_not_use_another(runner_factory):
    runner_factory(SYSTEM_WINE, "system")
    command = object.__new__(WineCommand)
    command.config = BottleConfig(Runner="missing-user-runner")
    assert command._get_runner_info() == (None, "")
    assert command.config.Runner == "missing-user-runner"


def test_proton_distribution_layout(runner_factory):
    info = runner_factory("proton")
    root = Path(info.root)
    (root / "files").mkdir()
    (root / "bin").rename(root / "files/bin")
    (root / "toolmanifest.vdf").write_text(
        '"manifest" { "compatmanager_layer_name" "proton" }'
    )
    discovered = RunnerRegistry.inspect("proton", str(root))
    assert discovered.wine == str(root / "files/bin/wine")
    assert discovered.wineserver == str(root / "files/bin/wineserver")


def test_remote_runner_update_is_rejected(manager):
    result = manager.apply_component_update(
        BottleConfig(Runner="local"), {"id": "runner", "latest": "remote"},
    )
    assert not result.ok


def test_failed_system_version_probe_is_not_available(runner_factory, monkeypatch):
    info = runner_factory("system-wine", "system")
    monkeypatch.setattr(runners.shutil, "which", lambda _: info.wine)
    monkeypatch.setattr(
        runners.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=126, stdout=""),
    )
    assert RunnerRegistry.system() is None


def test_system_and_user_runner_with_same_name_are_distinct(
    manager, runner_factory, monkeypatch, tmp_path
):
    info = runner_factory("winexxx")
    system_root = tmp_path / "system" / "winexxx"
    system_root.parent.mkdir()
    Path(info.root).rename(system_root)
    user = runner_factory("winexxx")
    manager.data_mgr.set(UserDataKeys.UserRunners, {"winexxx": user.root})
    monkeypatch.setattr(Paths, "system_runners", (str(system_root.parent),))
    monkeypatch.setenv("FLATPAK_ID", "com.usebottles.bottles")
    monkeypatch.setattr(
        runners.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="wine-11.0\n"),
    )
    assert manager.check_runners()
    assert manager.runners_available == ["system:winexxx", "winexxx"]
    assert manager.get_default_runner() == "system:winexxx"
    assert RunnerRegistry.entries["system:winexxx"].source == "system"
    assert RunnerRegistry.entries["winexxx"].source == "user"
    assert ManagerUtils.get_runner_path("system:winexxx") == str(system_root)
    assert not manager.remove_user_runner("system:winexxx").ok
    assert (system_root / "bin/wine").exists()


def test_path_wine_is_discovered_in_the_current_environment(manager, monkeypatch, runner_factory):
    system = runner_factory(SYSTEM_WINE, "system")
    monkeypatch.setattr(RunnerRegistry, "system", lambda: system)
    monkeypatch.setenv("FLATPAK_ID", "com.usebottles.bottles")
    assert manager.check_runners()
    assert manager.runners_available == [SYSTEM_WINE]


def test_system_runner_search_order_is_stable(runner_factory, tmp_path, monkeypatch):
    root = tmp_path / "packages"
    first = root / "local"
    second = root / "vendor"
    info = runner_factory("wine-stable")
    first.mkdir(parents=True)
    Path(info.root).rename(first / "wine-stable")
    info = runner_factory("wine-stable")
    second.mkdir()
    Path(info.root).rename(second / "wine-stable")
    monkeypatch.setattr(
        runners.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="wine-11.0\n"),
    )
    found = RunnerRegistry.packaged((str(first), str(second)))
    assert found["system:wine-stable"].root == str(first / "wine-stable")
    assert found["system:wine-stable"].version == "wine-11.0"
