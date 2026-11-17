import shlex
from pathlib import Path

import pytest

from bottles.backend.globals import Paths
from bottles.backend.managers import steam as steam_module
from bottles.backend.managers.steam import SteamManager
from bottles.backend.models.config import BottleConfig
from bottles.backend.utils import vdf
from bottles.backend.utils.steam import SteamUtils


def _write_vdf(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as vdf_file:
        vdf.dump(data, vdf_file, pretty=True)


def test_steam_path_skips_directory_without_steam_data(tmp_path, monkeypatch):
    steam_root = tmp_path / ".steam" / "debian-installation"
    (steam_root / "steamapps").mkdir(parents=True)
    config_dir = steam_root / "userdata" / "123" / "config"
    config_dir.mkdir(parents=True)

    misleading_path = tmp_path / ".local" / "share" / "Steam"
    misleading_path.parent.mkdir(parents=True)
    misleading_path.symlink_to(tmp_path / ".steam", target_is_directory=True)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "bottles.backend.managers.steam.ManagerUtils.get_bottle_path",
        lambda _config: "/bottle",
    )
    monkeypatch.setattr(
        "bottles.backend.managers.steam.ManagerUtils.extract_icon",
        lambda _config, _name, _path: "icon",
    )

    manager = SteamManager(BottleConfig(Name="Test"))
    result = manager.add_shortcut("Game", "/bottle/game.exe")

    assert manager.steam_path == str(steam_root)
    assert manager.steamapps_path == str(steam_root / "steamapps")
    assert manager.userdata_path == str(steam_root / "userdata")
    assert result.ok
    assert (config_dir / "shortcuts.vdf").is_file()


def test_steam_path_keeps_install_without_user_data(tmp_path, monkeypatch):
    steam_root = (
        tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
    )
    (steam_root / "ubuntu12_32").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    manager = SteamManager(check_only=True)

    assert manager.steam_path == str(steam_root)


@pytest.mark.parametrize(
    ("flatpak_id", "expected_exe", "expected_prefix"),
    [
        (None, "bottles-cli", ["run"]),
        (
            "com.usebottles.bottles",
            "flatpak",
            [
                "run",
                "--command=bottles-cli",
                "com.usebottles.bottles",
                "run",
            ],
        ),
    ],
)
def test_steam_shortcut_quotes_apostrophes(
    tmp_path, monkeypatch, flatpak_id, expected_exe, expected_prefix
):
    config_dir = tmp_path / "userdata" / "123" / "config"
    config_dir.mkdir(parents=True)

    manager = object.__new__(SteamManager)
    manager.config = BottleConfig(Name="Hero's bottle")
    manager.userdata_path = str(tmp_path / "userdata")

    if flatpak_id:
        monkeypatch.setenv("FLATPAK_ID", flatpak_id)
    else:
        monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(
        "bottles.backend.managers.steam.ManagerUtils.get_bottle_path",
        lambda _config: "/bottle",
    )
    monkeypatch.setattr(
        "bottles.backend.managers.steam.ManagerUtils.extract_icon",
        lambda _config, _name, _path: "icon",
    )

    result = manager.add_shortcut("Alice's Game", "/bottle/game.exe")

    with open(config_dir / "shortcuts.vdf", "rb") as shortcuts_file:
        shortcut = vdf.binary_loads(shortcuts_file.read())["shortcuts"]["0"]

    assert result.ok
    assert shortcut["Exe"] == expected_exe
    assert shlex.split(shortcut["LaunchOptions"]) == expected_prefix + [
        "-b",
        "Hero's bottle",
        "-p",
        "Alice's Game",
    ]


def test_non_steam_shortcut_appid_falls_back_to_crc():
    shortcut = {
        "Exe": '"/games/example.exe"',
        "AppName": "GE Shortcut",
    }

    assert SteamManager._get_shortcut_appid(shortcut) == 3641742335


def test_non_steam_launch_options_are_saved_to_shortcuts_vdf(tmp_path):
    appid = 4218887470
    config_dir = tmp_path / "userdata" / "123" / "config"
    config_dir.mkdir(parents=True)
    shortcuts_path = config_dir / "shortcuts.vdf"
    unrelated = {
        "appid": -1,
        "AppName": "Unrelated",
        "Exe": '"/games/other.exe"',
        "LaunchOptions": "--unchanged",
    }
    trailing_data = b"steam-extra-data"
    shortcuts_path.write_bytes(
        vdf.binary_dumps(
            {
                "shortcuts": {
                    "0": {
                        "appid": appid - 2**32,
                        "AppName": "GE Shortcut",
                        "Exe": '"/games/example.exe"',
                        "LaunchOptions": "DXVK_HUD=1 %command% --old",
                    },
                    "1": unrelated,
                }
            }
        )
        + trailing_data
    )
    manager = object.__new__(SteamManager)
    manager.userdata_path = str(tmp_path / "userdata")
    manager.localconfig = {}

    manager.set_launch_options(
        str(appid),
        {"command": "gamemoderun", "env_vars": {"FOO": "bar"}},
    )

    data = vdf.binary_loads(shortcuts_path.read_bytes(), raise_on_remaining=False)[
        "shortcuts"
    ]
    command, args, env_vars = SteamUtils.handle_launch_options(
        data["0"]["LaunchOptions"]
    )
    assert command == "gamemoderun"
    assert args.strip() == "--old"
    assert env_vars == {"DXVK_HUD": "1", "FOO": "bar"}
    assert data["1"] == unrelated
    assert shortcuts_path.read_bytes().endswith(trailing_data)


def test_regular_steam_launch_options_are_saved_to_localconfig(tmp_path):
    manager = object.__new__(SteamManager)
    manager.userdata_path = None
    manager.localconfig_path = str(tmp_path / "localconfig.vdf")
    manager.localconfig = {
        "UserLocalConfigStore": {
            "Software": {
                "Valve": {
                    "Steam": {
                        "Apps": {"123": {"LaunchOptions": "DXVK_HUD=1 %command% --old"}}
                    }
                }
            }
        }
    }

    manager.set_launch_options(
        "123",
        {"command": "gamemoderun", "env_vars": {"FOO": "bar"}},
    )

    launch_options = manager.localconfig["UserLocalConfigStore"]["Software"]["Valve"][
        "Steam"
    ]["Apps"]["123"]["LaunchOptions"]
    command, args, env_vars = SteamUtils.handle_launch_options(launch_options)
    assert command == "gamemoderun"
    assert args.strip() == "--old"
    assert env_vars == {"DXVK_HUD": "1", "FOO": "bar"}


def test_malformed_shortcuts_file_is_ignored(tmp_path):
    config_dir = tmp_path / "userdata" / "123" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "shortcuts.vdf").write_bytes(b"not a binary vdf")
    manager = object.__new__(SteamManager)
    manager.userdata_path = str(tmp_path / "userdata")

    assert manager.list_shortcuts() == {}
