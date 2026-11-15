"""Core Manager tests"""

from pathlib import Path

import pytest

from bottles.backend.managers import manager as manager_module
from bottles.backend.managers.data import DataManager, UserDataKeys
from bottles.backend.managers.manager import Manager
from bottles.backend.models.config import BottleConfig
from bottles.backend.utils.connection import ConnectionUtils
from bottles.backend.utils.gsettings_stub import GSettingsStub


@pytest.fixture(autouse=True)
def reset_manager_singleton():
    existing = Manager._instances.pop(Manager, None)
    if existing:
        for tracker in existing._playtime_trackers.values():
            tracker.shutdown()

    yield

    existing = Manager._instances.pop(Manager, None)
    if existing:
        for tracker in existing._playtime_trackers.values():
            tracker.shutdown()


def test_manager_is_singleton():
    assert Manager(is_cli=True) is Manager(
        is_cli=True
    ), "Manager should be singleton object"
    assert Manager(is_cli=True) is Manager(
        g_settings=GSettingsStub(), is_cli=True
    ), "Manager should be singleton even with different argument"


def test_manager_default_gsettings_stub():
    assert Manager().settings.get_boolean("anything") is False


def test_delete_sandboxed_bottle_does_not_restart_wine(
    mocker, monkeypatch, tmp_path
):
    bottles_path = tmp_path / "bottles"
    bottle_path = bottles_path / "Sandboxed"
    bottle_path.mkdir(parents=True)
    config = BottleConfig(
        Name="Sandboxed",
        Path=str(bottle_path),
        Runner="soda-11.0-5",
        Environment="Gaming",
    )
    config.Parameters.sandbox = True

    bottle_path.chmod(0o700)
    (bottle_path / "drive_c").mkdir()
    assert config.dump(str(bottle_path / "bottle.yml")).ok
    from bottles.backend.managers.storage import BottleIndex
    BottleIndex().register(str(bottle_path))
    monkeypatch.setattr(
        manager_module.Paths, "applications", str(tmp_path / "applications")
    )
    wineboot = mocker.patch.object(manager_module, "WineBoot")
    wineserver = mocker.patch.object(manager_module, "WineServer").return_value
    library = mocker.patch.object(manager_module, "LibraryManager").return_value
    library.get_library.return_value = {
        "game": {"bottle": {"name": "Sandboxed"}},
    }
    signal_send = mocker.patch.object(manager_module.SignalManager, "send")
    manager = object.__new__(Manager)
    manager.check_bottles = mocker.Mock()
    manager._playtime_trackers = {}

    assert manager.delete_bottle(config) is True
    assert not bottle_path.exists()
    wineboot.assert_not_called()
    wineserver.force_kill.assert_called_once_with()
    wineserver.wait.assert_not_called()
    library.remove_from_library.assert_called_once_with("game")
    manager.check_bottles.assert_called_once_with(silent=True)
    signal_send.assert_not_called()


def test_manager_cli_checks_connection_when_online(mocker):
    check_connection = mocker.patch.object(
        ConnectionUtils,
        "check_connection",
        autospec=True,
        return_value=True,
    )

    Manager(is_cli=True)
    check_connection.assert_called_once()


def test_manager_forced_offline_setting_skips_connection_check(mocker):
    class ForcedOfflineSettings(GSettingsStub):
        @staticmethod
        def get_boolean(key: str) -> bool:
            if key == "force-offline":
                return True
            return GSettingsStub.get_boolean(key)

    class EmptyChecksResult:
        data = {}

    check_connection = mocker.patch.object(
        ConnectionUtils,
        "check_connection",
        autospec=True,
        return_value=True,
    )
    checks = mocker.patch.object(
        Manager,
        "checks",
        autospec=True,
        return_value=EmptyChecksResult(),
    )

    manager = Manager(g_settings=ForcedOfflineSettings(), is_cli=False)

    assert manager.utils_conn.force_offline is True
    check_connection.assert_not_called()
    checks.assert_called_once()


def test_startup_does_not_create_a_prefix(tmp_path):
    from bottles.backend.globals import Paths
    manager = Manager(check_connection=False, is_cli=True)
    manager.check_app_dirs()
    assert not (Path(Paths.base) / "bottles").exists()
    assert manager._playtime_trackers == {}


def test_get_programs_preserves_per_program_runtime_options(monkeypatch):
    class Settings:
        @staticmethod
        def get_boolean(_key):
            return False

    class WindowsPath:
        @staticmethod
        def is_windows(_path):
            return False

    class WindowsSteam:
        is_steam_supported = False

    manager = object.__new__(Manager)
    manager._programs_cache = {}
    manager.settings = Settings()
    config = BottleConfig(
        Name="Test",
        External_Programs={
            "program-id": {
                "id": "program-id",
                "name": "Example",
                "executable": "example.exe",
                "path": "/games/example.exe",
                "environment": {"DXVK_HUD": "fps"},
                "arguments": "--safe-mode",
                "arguments_enabled": False,
                "d7vk": False,
                "discrete_gpu": True,
                "fsr": True,
                "gamemode": True,
                "latencyflex": False,
                "sync": "esync",
                "hide_console": True,
                "file_extensions": [".txt", ".json"],
                "automatic_backup": {
                    "enabled": True,
                    "destination": "/backups",
                    "paths": ["%BOTTLE_PATH%/save.dat"],
                    "keep": 3,
                },
            }
        },
    )

    monkeypatch.setattr(manager_module, "glob", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(manager_module, "WinePath", lambda _config: WindowsPath())
    monkeypatch.setattr(
        manager_module.ManagerUtils, "get_bottle_path", lambda _config: "/bottle"
    )
    monkeypatch.setattr(
        manager_module, "SteamManager", lambda *_args, **_kwargs: WindowsSteam()
    )

    program = Manager.get_programs(manager, config)[0]

    assert program["environment"] == {"DXVK_HUD": "fps"}
    assert program["arguments"] == "--safe-mode"
    assert program["arguments_enabled"] is False
    assert program["d7vk"] is False
    assert program["discrete_gpu"] is True
    assert program["fsr"] is True
    assert program["gamemode"] is True
    assert program["latencyflex"] is False
    assert program["sync"] == "esync"
    assert program["hide_console"] is True
    assert program["file_extensions"] == [".txt", ".json"]
    assert program["automatic_backup"] == {
        "enabled": True,
        "destination": "/backups",
        "paths": ["%BOTTLE_PATH%/save.dat"],
        "keep": 3,
    }


@pytest.mark.parametrize(
    ("arguments_enabled", "expected_names"),
    [
        (True, ["Renamed Game"]),
        (False, ["Renamed Game", "Original Folder Name"]),
    ],
)
def test_get_programs_deduplicates_renamed_epic_game(
    monkeypatch, arguments_enabled, expected_names
):
    class Settings:
        @staticmethod
        def get_boolean(key):
            return key == "epic-games"

    class WindowsPath:
        @staticmethod
        def is_windows(_path):
            return True

    class WindowsSteam:
        is_steam_supported = False

    path = (
        "C:\\Program Files (x86)\\Epic Games\\Launcher\\Portal\\Binaries\\Win32\\"
        "EpicGamesLauncher.exe"
    )
    arguments = "-opengl -com.epicgames.launcher://apps/game?action=launch"
    manager = object.__new__(Manager)
    manager._programs_cache = {}
    manager.settings = Settings()
    config = BottleConfig(
        Name="Test",
        External_Programs={
            "game-id": {
                "id": "game-id",
                "name": "Renamed Game",
                "executable": "EpicGamesLauncher.exe",
                "path": path,
                "folder": "C:\\Program Files (x86)\\Epic Games\\Launcher",
                "arguments": arguments,
                "arguments_enabled": arguments_enabled,
            }
        },
    )
    discovered = {
        "id": "discovered-id",
        "name": "Original Folder Name",
        "executable": "EpicGamesLauncher.exe",
        "path": path,
        "folder": "C:\\Program Files (x86)\\Epic Games\\Launcher",
        "arguments": arguments,
    }

    monkeypatch.setattr(manager_module, "glob", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(manager_module, "WinePath", lambda _config: WindowsPath())
    monkeypatch.setattr(
        manager_module.ManagerUtils, "get_bottle_path", lambda _config: "/bottle"
    )
    monkeypatch.setattr(
        manager_module.ManagerUtils,
        "get_exe_parent_dir",
        lambda *_args: "C:\\Program Files (x86)\\Epic Games\\Launcher",
    )
    monkeypatch.setattr(
        manager_module, "SteamManager", lambda *_args, **_kwargs: WindowsSteam()
    )
    monkeypatch.setattr(
        manager_module.EpicGamesStoreManager,
        "is_epic_supported",
        lambda _config: True,
    )
    monkeypatch.setattr(
        manager_module.EpicGamesStoreManager,
        "get_installed_games",
        lambda _config: [discovered],
    )

    programs = Manager.get_programs(manager, config)

    assert [program["name"] for program in programs] == expected_names


def test_missing_runner_stops_creation_before_component_download(mocker, tmp_path):
    from bottles.backend.utils.runners import RunnerRegistry

    manager = object.__new__(Manager)
    manager.runners_available = []
    manager.check_dxvk = mocker.Mock()
    mocker.patch.object(RunnerRegistry, "entries", {})

    result = manager.create_bottle(name="Test", environment="application", path=str(tmp_path))

    assert not result.ok
    assert "Runner is unavailable" in result.message
    manager.check_dxvk.assert_not_called()


class ComponentUpdateSettings:
    def __init__(self, show_updates=True, release_candidate=False):
        self.show_updates = show_updates
        self.release_candidate = release_candidate

    def get_boolean(self, key: str) -> bool:
        return {
            "show-component-updates": self.show_updates,
            "release-candidate": self.release_candidate,
        }[key]


def test_component_updates_can_be_disabled_globally(mocker):
    manager = object.__new__(Manager)
    manager.settings = ComponentUpdateSettings(show_updates=False)
    manager._Manager__collect_winebridge_update = mocker.Mock()
    config = BottleConfig()

    assert Manager.get_component_updates(manager, config) == []
    manager._Manager__collect_winebridge_update.assert_not_called()


def test_runner_updates_are_absent():
    manager = _make_update_manager(False)
    config = BottleConfig(Runner="soda-10.0-1")
    assert Manager.get_component_updates(manager, config) == []


def _make_update_manager(release_candidate: bool) -> Manager:
    manager = object.__new__(Manager)
    manager.settings = ComponentUpdateSettings(release_candidate=release_candidate)
    manager.supported_d7vk = {}
    manager.supported_dxvk = {}
    manager.supported_vkd3d = {}
    manager.supported_nvapi = {}
    manager.supported_latencyflex = {}
    manager.supported_winebridge = {}
    manager.winebridge_available = []
    return manager


@pytest.mark.parametrize("prerelease_channel", ["rc", "unstable"])
@pytest.mark.parametrize(
    ("release_candidate", "expected"),
    [(False, "dxvk-2.7.1"), (True, "dxvk-3.0-1")],
)
def test_component_updates_respect_release_channel(
    prerelease_channel, release_candidate, expected
):
    manager = _make_update_manager(release_candidate)
    manager.supported_dxvk = {
        "dxvk-3.0-1": {"Channel": prerelease_channel},
        "dxvk-2.7.1": {"Channel": "stable"},
    }
    config = BottleConfig(DXVK="dxvk-2.6.2")
    config.Parameters.dxvk = True

    updates = Manager.get_component_updates(manager, config)

    assert {update["id"]: update["latest"] for update in updates} == {"dxvk": expected}


def test_d7vk_updates_are_reported():
    manager = _make_update_manager(False)
    manager.supported_d7vk = {
        "d7vk-v2.0": {"Channel": "stable"},
        "d7vk-v1.0": {"Channel": "stable"},
    }
    config = BottleConfig(D7VK="d7vk-v1.0")
    config.Parameters.d7vk = True

    updates = Manager.get_component_updates(manager, config)

    assert {update["id"]: update["latest"] for update in updates} == {
        "d7vk": "d7vk-v2.0"
    }


def test_check_d7vk_clears_stale_available_versions():
    manager = object.__new__(Manager)
    manager.d7vk_available = ["d7vk-v1.0"]
    manager._Manager__check_component = lambda *_args: []

    assert Manager.check_d7vk(manager, False)
    assert manager.d7vk_available == []


def test_get_programs_can_refresh_cached_results(monkeypatch):
    class Settings:
        @staticmethod
        def get_boolean(_key):
            return False

    class WindowsPath:
        @staticmethod
        def is_windows(_path):
            return False

    class WindowsSteam:
        is_steam_supported = False

    cached = [{"name": "Cached program"}]
    manager = object.__new__(Manager)
    manager._programs_cache = {"Test": cached}
    manager.settings = Settings()
    config = BottleConfig(Name="Test")

    monkeypatch.setattr(manager_module, "glob", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(manager_module, "WinePath", lambda _config: WindowsPath())
    monkeypatch.setattr(
        manager_module.ManagerUtils, "get_bottle_path", lambda _config: "/bottle"
    )
    monkeypatch.setattr(
        manager_module, "SteamManager", lambda *_args, **_kwargs: WindowsSteam()
    )

    assert Manager.get_programs(manager, config) is cached
    assert Manager.get_programs(manager, config, force_update=True) == []
