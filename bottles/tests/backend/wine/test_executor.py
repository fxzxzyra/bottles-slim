"""Unit tests for WineExecutor placeholder handling"""

import os
import shlex
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bottles.backend.dlls.d7vk import D7VKComponent
from bottles.backend.dlls.dxvk import DXVKComponent
from bottles.backend.models.config import BottleConfig, BottleParams
from bottles.backend.models.result import Result
from bottles.backend.models.samples import Samples
from bottles.backend.utils.manager import ManagerUtils
from bottles.backend.wine import winecommand
from bottles.backend.wine.executor import WineExecutor
from bottles.backend.wine.winecommand import (
    WineCommand,
    WineEnv,
    apply_frame_rate_limit,
    apply_hdr_preferences,
    apply_wayland_preferences,
)


def _gamescope_command(config, runner):
    command = WineCommand.__new__(WineCommand)
    command.config = config
    command.runner = str(runner)
    command.minimal = False
    command.gamescope_activated = True
    command.arguments = ""
    return command


def _make_config(
    name: str = "TestBottle", path: str = "TestBottlePath"
) -> BottleConfig:
    return BottleConfig(Name=name, Path=os.path.abspath(path), Environment="Custom")


def test_gamescope_mangohud_payload_exits_with_the_game(monkeypatch, tmp_path):
    config = BottleConfig(Path=str(tmp_path))
    config.Parameters.gamescope = True
    config.Parameters.gamescope_fullscreen = False
    config.Parameters.mangohud = True

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mangoapp_pid = tmp_path / "mangoapp.pid"
    runner = bin_dir / "runner"
    runner.write_text(
        "#!/usr/bin/env sh\n"
        f'while [ ! -s "{mangoapp_pid}" ]; do sleep 0.01; done\n'
        "exit 23\n"
    )
    runner.chmod(0o755)
    mangoapp = bin_dir / "mangoapp"
    mangoapp.write_text(
        "#!/usr/bin/env sh\n"
        f'echo $$ > "{mangoapp_pid}"\n'
        "while :; do sleep 1; done\n"
    )
    mangoapp.chmod(0o755)

    command = _gamescope_command(config, runner)
    monkeypatch.setattr(winecommand, "gamescope_available", "gamescope")
    monkeypatch.setattr(winecommand, "gamemode_available", False)
    monkeypatch.setattr(winecommand, "mangohud_available", "mangohud")
    monkeypatch.setattr(winecommand, "obs_vkc_available", False)

    gamescope_command = command.get_cmd("app.exe")
    arguments = shlex.split(gamescope_command)
    launcher = arguments[arguments.index("--") + 1:]
    environment = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

    result = subprocess.run(launcher, env=environment, timeout=5, check=False)

    pid = int(mangoapp_pid.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        pytest.fail("mangoapp remained alive after the game exited")
    assert result.returncode == 23


@pytest.mark.parametrize("refresh_ok", [True, False])
def test_changed_fonts_refresh_before_launch(monkeypatch, tmp_path, refresh_ok):
    fonts = tmp_path / "drive_c/windows/Fonts"
    fonts.mkdir(parents=True)
    stamp = tmp_path / ".fonts_stamp"
    commands = []
    events = []

    class Command:
        def __init__(self, _config, **kwargs):
            commands.append(kwargs)

        def run(self):
            events.append("refresh")
            return Result(refresh_ok)

    monkeypatch.setattr(
        "bottles.backend.wine.wineprogram.WineCommand", Command
    )
    monkeypatch.setattr(
        ManagerUtils, "get_bottle_path", lambda _config: str(tmp_path)
    )
    monkeypatch.setattr(
        "bottles.backend.wine.executor.SignalManager.send", lambda *_args: None
    )
    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.exec_path = executor._raw_exec_path = r"C:\fixture.exe"
    executor.exec_type = "exe"

    def launch():
        events.append("launch")
        return Result(True)

    executor._WineExecutor__launch_with_bridge = launch

    assert executor.run().ok
    assert events == ["refresh", "launch"]
    assert commands[0]["command"] == "wineboot -u /nogui"
    assert commands[0]["communicate"] is True
    assert commands[0]["forced_dll_overrides"] == "mscoree=d"
    assert stamp.exists() == refresh_ok
    if refresh_ok:
        assert float(stamp.read_text()) == fonts.stat().st_mtime

    assert executor.run().ok
    assert len(commands) == (1 if refresh_ok else 2)


def test_build_placeholder_map_uses_program_values():
    config = _make_config()
    program = {
        "name": "My Game",
        "path": "/opt/games/my-game.exe",
    }

    placeholders = WineExecutor._build_placeholder_map(config, program)

    expected_bottle_path = ManagerUtils.get_bottle_path(config)
    assert placeholders["PROGRAM_NAME"] == "My Game"
    assert placeholders["PROGRAM_PATH"] == "/opt/games/my-game.exe"
    assert placeholders["PROGRAM_DIR"] == "/opt/games"
    assert placeholders["BOTTLE_NAME"] == "TestBottle"
    assert placeholders["BOTTLE_PATH"] == expected_bottle_path


def test_replace_placeholders_handles_unknown_tokens():
    placeholders = {"PROGRAM_NAME": "Example", "BOTTLE_NAME": "Bottle"}

    result = WineExecutor._replace_placeholders(
        "run-%PROGRAM_NAME%-on-%BOTTLE_NAME%-%UNKNOWN%",
        placeholders,
    )

    assert result == "run-Example-on-Bottle-%UNKNOWN%"


def test_run_program_substitutes_placeholders(monkeypatch):
    def fake_init(
        self,
        *,
        config,
        exec_path,
        args="",
        terminal=False,
        environment=None,
        move_file=False,
        move_upd_fn=None,
        pre_script=None,
        post_script=None,
        pre_script_args=None,
        post_script_args=None,
        cwd=None,
        monitoring=None,
        program_d7vk=None,
        program_dxvk=None,
        program_vkd3d=None,
        program_nvapi=None,
        program_gamescope=None,
        program_virt_desktop=None,
        program_winebridge=None,
        program_hide_console=False,
        sandbox_override=None,
    ):
        # mimic original __init__ contract enough for run() stub
        self.config = config
        self.use_winebridge = (
            program_winebridge
            if program_winebridge is not None
            else config.Parameters.winebridge
        )
        self.captured = {
            "config": config,
            "exec_path": exec_path,
            "args": args,
            "environment": environment,
            "pre_script": pre_script,
            "post_script": post_script,
            "pre_script_args": pre_script_args,
            "post_script_args": post_script_args,
            "cwd": cwd,
            "program_d7vk": program_d7vk,
            "program_dxvk": program_dxvk,
            "program_nvapi": program_nvapi,
            "program_hide_console": program_hide_console,
        }

    def fake_run(self):
        self.captured["use_winebridge"] = self.use_winebridge
        return Result(True, data=self.captured)

    monkeypatch.setattr(WineExecutor, "__init__", fake_init, raising=False)
    monkeypatch.setattr(WineExecutor, "run", fake_run, raising=False)

    config = _make_config(name="Bottle", path="BottlePath")
    config.Parameters.dxvk = True
    program = {
        "name": "Awesome Game",
        "path": "/games/awesome/game.exe",
        "arguments": "--title=%PROGRAM_NAME%",
        "pre_script": "/scripts/%BOTTLE_NAME%/%PROGRAM_NAME%.sh",
        "pre_script_args": "--prefix=%BOTTLE_PATH%",
        "post_script": None,
        "post_script_args": "--dir=%PROGRAM_DIR%",
        "folder": "%PROGRAM_DIR%",
        "environment": {
            "DXVK_HUD": "fps",
            "WINEDLLOVERRIDES": "version=n,b",
            "WINEARCH": "win32",
            "WINEPREFIX": "/tmp/other",
        },
        "dxvk": False,
        "dxvk_nvapi": True,
        "gamemode": True,
        "sync": "esync",
        "winebridge": True,
        "hide_console": True,
    }

    result = WineExecutor.run_program(config=config, program=program, terminal=False)

    assert result.status is True
    data = result.data
    assert data["exec_path"] == "/games/awesome/game.exe"
    assert data["args"] == "--title=Awesome Game"
    assert data["pre_script"] == "/scripts/Bottle/Awesome Game.sh"
    assert data["pre_script_args"] == f"--prefix={ManagerUtils.get_bottle_path(config)}"
    assert data["post_script_args"] == "--dir=/games/awesome"
    assert data["cwd"] == "/games/awesome"
    assert data["environment"] == {
        "DXVK_HUD": "fps",
        "WINEDLLOVERRIDES": "version=n,b",
    }
    assert data["program_dxvk"] is False
    assert data["program_nvapi"] is True
    assert data["program_hide_console"] is True
    assert data["config"] is not config
    assert data["config"].Parameters.dxvk is True
    assert data["config"].Parameters.dxvk_nvapi is False
    assert data["config"].Parameters.gamemode is True
    assert data["config"].Parameters.sync == "esync"
    assert data["use_winebridge"] is False
    assert config.Parameters.dxvk_nvapi is False
    assert config.Parameters.dxvk is True
    assert config.Parameters.gamemode is False
    assert config.Parameters.sync == "wine"


def test_run_program_creates_configured_backup_after_exit(monkeypatch):
    events = []

    def fake_init(self, **_kwargs):
        self.use_winebridge = True

    def fake_run(self):
        events.append("run")
        return Result(True, data={"use_winebridge": self.use_winebridge})

    monkeypatch.setattr(WineExecutor, "__init__", fake_init, raising=False)
    monkeypatch.setattr(
        WineExecutor,
        "run",
        fake_run,
        raising=False,
    )
    monkeypatch.setattr(
        "bottles.backend.managers.backup.BackupManager.create_program_backup",
        lambda _config, _program: events.append("backup") or Result(True),
    )
    config = _make_config()
    program = {
        "name": "Game",
        "path": "/games/game.exe",
        "automatic_backup": {
            "enabled": True,
            "destination": "/backups",
            "paths": ["/saves"],
        },
    }

    result = WineExecutor.run_program(config, program)

    assert result.status
    assert result.data["use_winebridge"] is False
    assert events == ["run", "backup"]


def test_run_program_preserves_custom_steam_app_id(monkeypatch):
    captured = {}

    def fake_init(self, **kwargs):
        captured.update(kwargs)
        self.use_winebridge = False

    monkeypatch.setattr(WineExecutor, "__init__", fake_init, raising=False)
    monkeypatch.setattr(
        WineExecutor,
        "run",
        lambda _self: Result(True),
        raising=False,
    )

    config = _make_config()
    config.Runner = "soda-11.0-3"
    WineExecutor.run_program(
        config=config,
        program={
            "id": "game-id",
            "name": "Game",
            "path": "/games/game.exe",
            "environment": {"SteamAppId": "123456"},
        },
    )

    assert captured["environment"]["SteamAppId"] == "123456"


@pytest.mark.parametrize("runner", ["soda-11.0-3", "dwproton-9-1", "wine-ge-8-26"])
def test_run_program_does_not_advertise_steam_to_proton_runners(monkeypatch, runner):
    captured = {}

    def fake_init(self, **kwargs):
        captured.update(kwargs)
        self.use_winebridge = True

    def fake_run(self):
        return Result(True, data={"use_winebridge": self.use_winebridge})

    monkeypatch.setattr(WineExecutor, "__init__", fake_init, raising=False)
    monkeypatch.setattr(WineExecutor, "run", fake_run, raising=False)

    config = _make_config()
    config.Runner = runner
    config.Parameters.use_steam_runtime = False
    program = {
        "id": "game-id",
        "name": "Game",
        "path": "/games/game.exe",
        "winebridge": True,
    }

    result = WineExecutor.run_program(config=config, program=program)

    assert "SteamAppId" not in captured["environment"]
    assert result.data["use_winebridge"] is True


def test_program_dxvk_false_adds_builtin_override(tmp_path):
    executable = tmp_path / "program.exe"
    executable.touch()
    config = _make_config()
    config.Parameters.dxvk = True

    executor = WineExecutor(
        config=config,
        exec_path=str(executable),
        program_dxvk=False,
    )

    assert executor.environment["WINEDLLOVERRIDES"] == (
        f"{DXVKComponent.get_override_keys()}=b"
    )


def test_global_dxvk_false_adds_builtin_override(tmp_path):
    executable = tmp_path / "program.exe"
    executable.touch()
    config = _make_config()
    config.Parameters.dxvk = False

    executor = WineExecutor(
        config=config,
        exec_path=str(executable),
    )

    assert executor.environment["WINEDLLOVERRIDES"] == (
        f"{DXVKComponent.get_override_keys()}=b"
    )


def test_program_dxvk_true_overrides_global_disabled_state(tmp_path):
    executable = tmp_path / "program.exe"
    executable.touch()
    config = _make_config()
    config.Parameters.dxvk = False

    executor = WineExecutor(
        config=config,
        exec_path=str(executable),
        program_dxvk=True,
    )

    assert "WINEDLLOVERRIDES" not in executor.environment


def test_program_d7vk_false_adds_builtin_override(tmp_path):
    executable = tmp_path / "program.exe"
    executable.touch()
    config = _make_config()
    config.Parameters.d7vk = True
    config.Parameters.dxvk = True

    executor = WineExecutor(
        config=config,
        exec_path=str(executable),
        program_d7vk=False,
    )

    assert executor.environment["WINEDLLOVERRIDES"] == (
        f"{D7VKComponent.get_override_keys()}=b"
    )


def test_winecommand_reports_nonzero_exit_status(monkeypatch):
    process = SimpleNamespace(
        returncode=7,
        communicate=lambda: (b"registry failed", None),
    )
    monkeypatch.setattr(
        winecommand.subprocess, "Popen", lambda *_args, **_kwargs: process
    )

    command = WineCommand.__new__(WineCommand)
    command.runner = "/usr/bin/wine"
    command.env = {}
    command.command = "wine reg import test.reg"
    command.config = _make_config()
    command.terminal = False
    command.sandbox_override = None
    command.communicate = True
    command.cwd = None

    result = command.run()

    assert not result.ok
    assert result.data == "registry failed"
    assert result.message == "Command exited with status 7."
    assert command.returncode == 7


def test_winecommand_reports_full_windows_exit_status(monkeypatch):
    process = SimpleNamespace(
        returncode=108,
        communicate=lambda: (b"setup failed\nBOTTLES_EXIT_CODE_test=17004\r\n", None),
    )
    monkeypatch.setattr(
        winecommand.subprocess, "Popen", lambda *_args, **_kwargs: process
    )

    command = WineCommand.__new__(WineCommand)
    command.runner = "/usr/bin/wine"
    command.env = {}
    command.command = "wine cmd.exe /d /c test.bat"
    command.config = _make_config()
    command.terminal = False
    command.sandbox_override = None
    command.communicate = True
    command.cwd = None
    command._exit_code_batch = None
    command._exit_code_marker = "BOTTLES_EXIT_CODE_test"

    result = command.run()

    assert not result.ok
    assert result.data == "setup failed"
    assert result.message == "Command exited with status 17004."
    assert command.returncode == 17004


def test_executable_launch_reports_winecommand_failure(monkeypatch):
    command_result = Result(False, data="setup failed", message="status 7")

    class Command:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self):
            return command_result

    monkeypatch.setattr("bottles.backend.wine.executor.WineCommand", Command)
    monkeypatch.setattr(
        WineExecutor,
        "_WineExecutor__set_monitors",
        lambda _self: None,
    )
    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.exec_path = "setup.exe"
    executor.args = "/silent"
    executor.terminal = False
    executor.environment = {}
    executor.pre_script = None
    executor.post_script = None
    executor.pre_script_args = None
    executor.post_script_args = None
    executor.cwd = None
    executor.sandbox_override = None

    result = executor._WineExecutor__launch_exe()

    assert not result.ok
    assert result.data == {"output": command_result}
    assert result.message == "status 7"


def test_component_override_bypasses_winebridge(monkeypatch):
    def fake_init(self, **kwargs):
        self.use_winebridge = kwargs["program_winebridge"]

    def fake_run(self):
        return Result(True, data={"use_winebridge": self.use_winebridge})

    monkeypatch.setattr(WineExecutor, "__init__", fake_init, raising=False)
    monkeypatch.setattr(WineExecutor, "run", fake_run, raising=False)

    result = WineExecutor.run_program(
        config=_make_config(),
        program={
            "path": "/games/example.exe",
            "dxvk": False,
            "winebridge": True,
        },
    )

    assert result.data["use_winebridge"] is False


def test_hide_console_bypasses_winebridge(monkeypatch):
    def fake_init(self, **kwargs):
        self.use_winebridge = kwargs["program_winebridge"]

    def fake_run(self):
        return Result(True, data={"use_winebridge": self.use_winebridge})

    monkeypatch.setattr(WineExecutor, "__init__", fake_init, raising=False)
    monkeypatch.setattr(WineExecutor, "run", fake_run, raising=False)

    result = WineExecutor.run_program(
        config=_make_config(),
        program={
            "path": "/games/example.exe",
            "hide_console": True,
            "winebridge": True,
        },
    )

    assert result.data["use_winebridge"] is False


def test_hide_console_routes_exe_through_start(monkeypatch):
    calls = []

    class FakeWinePath:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_unix(_path):
            return False

        @staticmethod
        def is_windows(_path):
            return False

    def fake_start(self, host_cwd=False):
        assert host_cwd is False
        calls.append("start")
        return Result(True)

    def fake_exe(self):
        calls.append("exe")
        return Result(True)

    monkeypatch.setattr("bottles.backend.wine.executor.WinePath", FakeWinePath)
    monkeypatch.setattr(
        WineExecutor,
        "_WineExecutor__launch_with_starter",
        fake_start,
    )
    monkeypatch.setattr(WineExecutor, "_WineExecutor__launch_exe", fake_exe)

    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.use_winebridge = False
    executor.use_virt_desktop = False
    executor.hide_console = True
    executor.exec_type = "exe"
    executor._raw_exec_path = r"C:\games\example.exe"
    executor.exec_path = "/games/example.exe"

    result = executor._WineExecutor__launch_with_bridge()

    assert result.status is True
    assert calls == ["start"]


def test_winebridge_preserves_terminal_launch(monkeypatch):
    captured = {}

    class FakeWineBridge:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_available():
            return True

        @staticmethod
        def run_exe(exec_path, **kwargs):
            captured["exec_path"] = exec_path
            captured.update(kwargs)
            return Result(True)

    class FakeWinePath:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_unix(_path):
            return False

    monkeypatch.setattr("bottles.backend.wine.executor.WineBridge", FakeWineBridge)
    monkeypatch.setattr("bottles.backend.wine.executor.WinePath", FakeWinePath)

    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.use_winebridge = True
    executor.exec_type = "exe"
    executor._raw_exec_path = r"C:\Games\example.exe"
    executor.terminal = True
    executor.environment = {"GAME_MODE": "1"}
    executor.cwd = r"C:\Games"
    executor.sandbox_override = "off"

    result = executor._WineExecutor__launch_with_bridge()

    assert result.status is True
    assert captured == {
        "exec_path": r"C:\Games\example.exe",
        "terminal": True,
        "environment": {"GAME_MODE": "1"},
        "cwd": r"C:\Games",
        "sandbox_override": "off",
    }


def test_hide_console_virtual_desktop_uses_background_explorer(monkeypatch):
    captured = {}

    class FakeExplorer:
        def __init__(self, _config):
            pass

        def launch_desktop(self, **kwargs):
            captured.update(kwargs)
            return Result(True, data="output")

    monkeypatch.setattr("bottles.backend.wine.executor.Explorer", FakeExplorer)

    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.config.Parameters.virtual_desktop_res = "1280x720"
    executor.exec_path = r"'C:\Program Files\Example\example.exe'"
    executor.args = "--safe-mode"
    executor.environment = {"DXVK_HUD": "fps"}
    executor.cwd = r"C:\Program Files\Example"
    executor.hide_console = True
    executor.sandbox_override = "off"
    executor.monitoring = []

    result = executor._WineExecutor__launch_with_explorer()

    assert result.status is True
    assert captured["background"] is True
    assert captured["sandbox_override"] == "off"


def test_virtual_desktop_converts_raw_unix_path_before_quoting(monkeypatch):
    captured = {}

    class FakeWinePath:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_unix(path):
            captured["checked_path"] = path
            return True

        @staticmethod
        def to_windows(path, native=False, sandbox_override=None):
            captured["converted_path"] = path
            captured["native"] = native
            captured["sandbox_override"] = sandbox_override
            return r"Z:\tmp\Test App.exe"

    def fake_explorer(self):
        return Result(True, data={"exec_path": self.exec_path})

    monkeypatch.setattr("bottles.backend.wine.executor.WinePath", FakeWinePath)
    monkeypatch.setattr(
        WineExecutor,
        "_WineExecutor__launch_with_explorer",
        fake_explorer,
    )

    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.use_winebridge = False
    executor.use_virt_desktop = True
    executor.hide_console = True
    executor.exec_type = "exe"
    executor._raw_exec_path = "/tmp/Test App.exe"
    executor.exec_path = "'/tmp/Test App.exe'"
    executor.sandbox_override = "off"

    result = executor._WineExecutor__launch_with_bridge()

    assert result.status is True
    assert captured["checked_path"] == "/tmp/Test App.exe"
    assert captured["converted_path"] == "/tmp/Test App.exe"
    assert captured["native"] is False
    assert captured["sandbox_override"] == "off"
    assert result.data["exec_path"] == r"'Z:\tmp\Test App.exe'"


def test_windows_executable_cwd_uses_its_parent(monkeypatch):
    captured = {}

    class FakeWinePath:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_windows(path):
            return ":" in path

        @staticmethod
        def to_unix(path, native=False):
            captured["windows_parent"] = path
            captured["native"] = native
            return "/prefix/drive_c/Program Files/Example"

    monkeypatch.setattr("bottles.backend.wine.executor.WinePath", FakeWinePath)

    executor = WineExecutor(
        config=_make_config(),
        exec_path=r"C:\Program Files\Example\example.exe",
    )

    assert captured["windows_parent"] == r"C:\Program Files\Example"
    assert captured["native"] is True
    assert executor.cwd == "/prefix/drive_c/Program Files/Example"


def test_winebridge_launch_preserves_spaces_in_executable_path(monkeypatch):
    executable = "/mnt/storage/DO NOT RENAME OR MOVE/Games/Poly Bridge 2.exe"
    captured = {}

    class FakeWineBridge:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_available():
            return True

        @staticmethod
        def run_exe(exec_path, **kwargs):
            captured["exec_path"] = exec_path
            captured.update(kwargs)
            return ""

    class FakeWinePath:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_unix(exec_path):
            return exec_path.startswith("/")

        @staticmethod
        def to_windows(exec_path, native=False):
            assert native is True
            return exec_path.replace("/", "\\")

    monkeypatch.setattr("bottles.backend.wine.executor.WineBridge", FakeWineBridge)
    monkeypatch.setattr("bottles.backend.wine.executor.WinePath", FakeWinePath)
    monkeypatch.setattr(
        "bottles.backend.wine.executor.ManagerUtils.get_bottle_path",
        lambda _config: "/mnt/storage/DO NOT RENAME OR MOVE",
    )

    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.use_winebridge = True
    executor.exec_type = "exe"
    executor._raw_exec_path = executable
    executor.exec_path = f"'{executable}'"
    executor.terminal = False
    executor.environment = {}
    executor.cwd = None
    executor.sandbox_override = None

    result = executor._WineExecutor__launch_with_bridge()

    assert result.status is True
    assert captured["exec_path"] == executable.replace("/", "\\")
    assert captured["terminal"] is False


def test_external_executable_uses_wine_start(monkeypatch):
    executable = "/games/KeePass Portable/KeePass.exe"
    captured = {}

    class FakeWineBridge:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_available():
            return True

    class FakeWinePath:
        def __init__(self, _config):
            pass

        @staticmethod
        def is_unix(path):
            return path.startswith("/")

        @staticmethod
        def is_windows(_path):
            return False

    monkeypatch.setattr("bottles.backend.wine.executor.WineBridge", FakeWineBridge)
    monkeypatch.setattr("bottles.backend.wine.executor.WinePath", FakeWinePath)
    monkeypatch.setattr(
        "bottles.backend.wine.executor.ManagerUtils.get_bottle_path",
        lambda _config: "/prefix",
    )
    monkeypatch.setattr(
        "bottles.backend.wine.executor.Start.run",
        lambda _self, **kwargs: captured.update(kwargs) or Result(True),
    )
    monkeypatch.setattr(
        WineExecutor,
        "_WineExecutor__set_monitors",
        lambda _self: None,
    )

    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.use_winebridge = True
    executor.use_virt_desktop = False
    executor.hide_console = False
    executor.exec_type = "exe"
    executor._raw_exec_path = executable
    executor.exec_path = shlex.quote(executable)
    executor.terminal = False
    executor.args = "--test"
    executor.environment = {"WINEDEBUG": "+seh"}
    executor.pre_script = None
    executor.post_script = None
    executor.pre_script_args = None
    executor.post_script_args = None
    executor.cwd = "/games/KeePass Portable"
    executor.sandbox_override = None

    result = executor._WineExecutor__launch_with_bridge()

    assert result.status is True
    assert captured["file"] == shlex.quote(executable)
    assert captured["cwd"] == "/games/KeePass Portable"
    assert captured["args"] == "--test"
    assert captured["environment"] == {"WINEDEBUG": "+seh"}
    assert captured["host_cwd"] is True


def test_wine_env_respects_allowed_keys(monkeypatch):
    monkeypatch.setenv("KEEP_ONLY", "1")
    monkeypatch.setenv("DROP_ME", "2")

    env = WineEnv(clean=False, allowed_keys=["KEEP_ONLY"])
    resolved = env.get()["envs"]

    assert resolved["KEEP_ONLY"] == "1"
    assert "DROP_ME" not in resolved


def test_default_wine_environment_inherits_xmodifiers(monkeypatch):
    monkeypatch.setenv("XMODIFIERS", "@im=fcitx")

    env = WineEnv(allowed_keys=Samples.default_inherited_environment)

    assert env.get()["envs"]["XMODIFIERS"] == "@im=fcitx"


@pytest.mark.parametrize(
    ("sync", "ntsync_available", "expected"),
    [
        ("wine", True, {"WINENTSYNC": "1"}),
        ("wine", False, {}),
        ("ntsync", True, {"WINENTSYNC": "1"}),
        ("ntsync", False, {"WINEFSYNC": "1"}),
        ("esync", False, {"WINEESYNC": "1"}),
        ("fsync", False, {"WINEFSYNC": "1"}),
    ],
)
def test_winecommand_applies_selected_sync_environment(
    monkeypatch, sync, ntsync_available, expected
):
    monkeypatch.setattr(
        winecommand,
        "is_ntsync_available",
        lambda _runner: ntsync_available,
    )
    env = WineEnv(clean=True)

    WineCommand._apply_sync_environment(env, sync, "/runner/bin/wine")

    assert env.get()["envs"] == expected


def test_frame_rate_limit_applies_to_dxvk_and_vkd3d():
    env = WineEnv(clean=True)
    env.add("DXVK_CONFIG", "dxgi.syncInterval = 0")

    apply_frame_rate_limit(env, BottleParams(frame_rate_limit=120))

    resolved = env.get()["envs"]
    assert resolved["DXVK_CONFIG"] == (
        "dxgi.syncInterval = 0; dxgi.maxFrameRate = 120; "
        "d3d9.maxFrameRate = 120"
    )
    assert resolved["VKD3D_FRAME_RATE"] == "120"


def test_frame_rate_limit_preserves_manual_environment_when_disabled():
    env = WineEnv(clean=True)
    env.add("DXVK_CONFIG", "dxgi.maxFrameRate = 90")
    env.add("VKD3D_FRAME_RATE", "90")

    apply_frame_rate_limit(env, BottleParams())

    resolved = env.get()["envs"]
    assert resolved["DXVK_CONFIG"] == "dxgi.maxFrameRate = 90"
    assert resolved["VKD3D_FRAME_RATE"] == "90"






def test_hdr_preferences_enable_dxvk_without_automatic_wayland_layer(monkeypatch):
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.DisplayUtils.display_server_type",
        lambda: "wayland",
    )
    env = WineEnv(clean=True)
    env.add("WAYLAND_DISPLAY", "wayland-0")
    params = BottleParams(hdr=True, wayland=True)

    apply_hdr_preferences(env, params, gamescope_activated=False)

    resolved = env.get()["envs"]
    assert resolved["DXVK_HDR"] == "1"
    assert "ENABLE_HDR_WSI" not in resolved


def test_hdr_preferences_do_not_enable_wayland_layer_for_gamescope():
    env = WineEnv(clean=True)
    env.add("ENABLE_HDR_WSI", "1")
    env.add("DISABLE_GAMESCOPE_WSI", "1")
    params = BottleParams(hdr=True, wayland=True)

    apply_hdr_preferences(env, params, gamescope_activated=True)

    resolved = env.get()["envs"]
    assert resolved["DXVK_HDR"] == "1"
    assert resolved["ENABLE_GAMESCOPE_WSI"] == "1"
    assert "ENABLE_HDR_WSI" not in resolved
    assert "DISABLE_GAMESCOPE_WSI" not in resolved


def test_gamescope_removes_hdr_wsi_when_hdr_is_disabled():
    env = WineEnv(clean=True)
    env.add("ENABLE_HDR_WSI", "1")

    apply_hdr_preferences(env, BottleParams(), gamescope_activated=True)

    assert "ENABLE_HDR_WSI" not in env.get()["envs"]


def test_native_wayland_enables_egl(monkeypatch):
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.DisplayUtils.display_server_type",
        lambda: "wayland",
    )
    env = WineEnv(clean=True)
    env.add("DISPLAY", ":1")
    env.add("WAYLAND_DISPLAY", "wayland-0")

    apply_wayland_preferences(env, BottleParams(wayland=True))

    resolved = env.get()["envs"]
    assert "DISPLAY" not in resolved
    assert resolved["WINE_USE_EGL"] == "1"


@pytest.mark.parametrize("session_type", [None, ""])
def test_native_wayland_without_session_type(monkeypatch, session_type):
    if session_type is None:
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    else:
        monkeypatch.setenv("XDG_SESSION_TYPE", session_type)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    env = WineEnv(clean=True)
    env.add("DISPLAY", ":1")
    env.add("WAYLAND_DISPLAY", "wayland-0")

    apply_wayland_preferences(env, BottleParams(wayland=True))

    resolved = env.get()["envs"]
    assert "DISPLAY" not in resolved
    assert resolved["WINE_USE_EGL"] == "1"


def test_hdr_preferences_require_native_wayland_for_hdr():
    env = WineEnv(clean=True)
    params = BottleParams(hdr=True, wayland=False)

    apply_hdr_preferences(env, params, gamescope_activated=False)

    resolved = env.get()["envs"]
    assert "DXVK_HDR" not in resolved
    assert "ENABLE_HDR_WSI" not in resolved


def test_hdr_preferences_preserve_manual_environment_when_disabled():
    env = WineEnv(clean=True)
    env.add("DXVK_HDR", "1")
    env.add("ENABLE_HDR_WSI", "1")

    apply_hdr_preferences(env, BottleParams(), gamescope_activated=False)

    resolved = env.get()["envs"]
    assert resolved["DXVK_HDR"] == "1"
    assert resolved["ENABLE_HDR_WSI"] == "1"






def test_winecommand_filters_host_environment(monkeypatch, tmp_path, runner_factory):
    runner_factory("test")
    bottle_path = tmp_path / "TestBottle"
    bottle_path.mkdir()
    runner_path = tmp_path / "runner"
    for sub in [
        "lib",
        "lib64",
        "lib/wine/x86_64-unix",
        "lib32/wine/x86_64-unix",
        "lib32",
        "lib64/wine/x86_64-unix",
        "lib/wine/i386-unix",
        "lib32/wine/i386-unix",
        "lib64/wine/i386-unix",
    ]:
        (runner_path / sub).mkdir(parents=True, exist_ok=True)

    config = BottleConfig(Name="Test", Path=str(bottle_path), Runner="test")
    params = BottleParams()
    params.use_runtime = False
    params.use_eac_runtime = False
    params.use_be_runtime = False
    params.hdr = True
    config.Parameters = params
    config.Limit_System_Environment = True
    config.Inherited_Environment_Variables = ["DISPLAY"]

    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("SHOULD_NOT_PASS", "secret")

    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_bottle_path",
        lambda _config: str(bottle_path),
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_runner_path",
        lambda _runner: str(runner_path),
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.DisplayUtils.check_nvidia_device",
        lambda: None,
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.DisplayUtils.display_server_type",
        lambda: "x11",
    )

    def _fake_gpu(self):
        return {
            "prime": {
                "discrete": None,
                "integrated": {"icd": "/tmp/icd", "envs": {}},
            },
            "vendors": {"generic": {"icd": "/tmp/icd", "envs": {}}},
        }

    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.GPUUtils.get_gpu",
        _fake_gpu,
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.RuntimeManager.get_runtime_env",
        lambda *_: [],
    )

    winecmd = WineCommand.__new__(WineCommand)
    winecmd.config = config
    winecmd.minimal = True
    winecmd.arguments = ""
    winecmd.runner = "/usr/bin/wine"
    winecmd.gamescope_activated = False
    winecmd.terminal = False

    env = winecmd.get_env()
    assert env["DISPLAY"] == ":1"
    assert "DXVK_HDR" not in env
    assert "SHOULD_NOT_PASS" not in env




def test_wayland_sandbox_clears_parent_display(monkeypatch, tmp_path):
    bottle_path = tmp_path / "TestBottle"
    bottle_path.mkdir()
    config = BottleConfig(Name="Test", Path=str(bottle_path), Runner="sys-wine")

    monkeypatch.setenv("FLATPAK_ID", "com.usebottles.bottles")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_bottle_path",
        lambda _config: str(bottle_path),
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_runner_path",
        lambda _runner: "sys-wine",
    )

    winecmd = WineCommand.__new__(WineCommand)
    winecmd.config = config
    winecmd.env = {"WAYLAND_DISPLAY": "wayland-0"}
    winecmd.cwd = str(bottle_path)
    winecmd.steam_runtime_root = None

    command = winecmd._get_sandbox_manager().get_cmd("wine")

    assert "--clear-env" not in command
    assert "env -i" in command
    assert "WAYLAND_DISPLAY=wayland-0" in command
    assert not any(token.startswith("DISPLAY=") for token in shlex.split(command))

    monkeypatch.delenv("FLATPAK_ID")
    command = winecmd._get_sandbox_manager().get_cmd("wine")

    assert command.index("--clearenv") < command.index(
        "--setenv WAYLAND_DISPLAY wayland-0"
    )


@pytest.mark.parametrize(
    ("use_steam_runtime", "runtime_symlink"),
    ((False, False), (True, False), (True, True)),
)
def test_dedicated_sandbox_uses_selected_runtime_path(
    monkeypatch, tmp_path, use_steam_runtime, runtime_symlink
):
    bottle_path = tmp_path / "TestBottle"
    bottle_path.mkdir()
    runner_path = tmp_path / "wine-runner"
    runner_path.mkdir()
    runtime_path = tmp_path / "SteamLinuxRuntime_sniper"
    if runtime_symlink:
        runtime_target = tmp_path / "SteamLinuxRuntime_sniper_target"
        runtime_target.mkdir()
        runtime_path.symlink_to(runtime_target, target_is_directory=True)
    else:
        runtime_path.mkdir()
    entry_point = runtime_path / "_v2-entry-point"
    entry_point.touch()

    config = BottleConfig(
        Name="Test",
        Path=str(bottle_path),
        Runner="wine-runner",
        Environment="Custom",
    )
    config.Parameters.use_steam_runtime = use_steam_runtime

    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_bottle_path",
        lambda _config: str(bottle_path),
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_runner_path",
        lambda _runner: str(runner_path),
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.resolve_portal_path",
        lambda path: path,
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.RuntimeManager.get_runtimes",
        lambda _category: {
            "sniper": {
                "name": "sniper",
                "entry_point": str(entry_point),
            }
        },
    )

    winecmd = WineCommand.__new__(WineCommand)
    winecmd.config = config
    winecmd.minimal = True
    winecmd.arguments = ""
    winecmd.runner = str(runner_path / "bin/wine")
    winecmd.gamescope_activated = False
    winecmd.cwd = str(bottle_path)
    winecmd.env = {}

    command = winecmd.get_cmd("cmd")
    sandbox = winecmd._get_sandbox_manager()

    invalid_runtime_path = os.path.realpath("sniper")
    assert invalid_runtime_path not in sandbox.share_paths_ro
    resolved_runtime = os.path.realpath(runtime_path)
    resolved_entry_point = os.path.realpath(entry_point)
    assert (resolved_runtime in sandbox.share_paths_ro) is use_steam_runtime
    assert (resolved_entry_point in command) is use_steam_runtime
    if use_steam_runtime and runtime_symlink:
        assert str(runtime_path) not in sandbox.share_paths_ro
        assert str(entry_point) not in command


@pytest.mark.parametrize(
    ("parameter", "wrapper"),
    (("gamemode", "/usr/bin/gamemoderun"), ("mangohud", "/usr/bin/mangohud")),
)
def test_host_wrappers_run_outside_steam_runtime(
    monkeypatch, tmp_path, parameter, wrapper
):
    runtime_path = tmp_path / "SteamLinuxRuntime_sniper"
    runtime_path.mkdir()
    entry_point = runtime_path / "_v2-entry-point"
    entry_point.touch()
    config = BottleConfig(Name="Test", Runner="wine-runner")
    config.Parameters.use_steam_runtime = True
    setattr(config.Parameters, parameter, True)

    monkeypatch.setattr(winecommand, "gamemode_available", "/usr/bin/gamemoderun")
    monkeypatch.setattr(winecommand, "mangohud_available", "/usr/bin/mangohud")
    monkeypatch.setattr(winecommand, "gamescope_available", False)
    monkeypatch.setattr(winecommand, "obs_vkc_available", False)
    monkeypatch.setattr(
        winecommand.RuntimeManager,
        "get_runtimes",
        lambda _category: {
            "sniper": {"name": "sniper", "entry_point": str(entry_point)}
        },
    )

    winecmd = WineCommand.__new__(WineCommand)
    winecmd.config = config
    winecmd.minimal = False
    winecmd.arguments = ""
    winecmd.runner = "/runner/bin/wine"
    winecmd.gamescope_activated = False

    command = winecmd.get_cmd("game.exe")

    assert command.index(wrapper) < command.index(str(entry_point))
    assert command.index(str(entry_point)) < command.index(winecmd.runner)


@pytest.mark.parametrize(
    ("runtime", "entry_point", "separator"),
    (
        ("steamrt4", "_v2-entry-point", " -- "),
        ("sniper", "_v2-entry-point", " -- "),
        ("soldier", "_v2-entry-point", " -- "),
        ("scout", "run.sh", " "),
    ),
)
def test_steam_runtime_uses_supported_command_separator(
    monkeypatch, tmp_path, runtime, entry_point, separator
):
    runtime_path = tmp_path / runtime
    runtime_path.mkdir()
    entry_point = runtime_path / entry_point
    entry_point.touch()
    config = BottleConfig(Name="Test", Runner="wine")
    config.Parameters.use_steam_runtime = True

    monkeypatch.setattr(
        winecommand.RuntimeManager,
        "get_runtimes",
        lambda _category: {
            runtime: {"name": runtime, "entry_point": str(entry_point)}
        },
    )

    winecmd = WineCommand.__new__(WineCommand)
    winecmd.config = config
    winecmd.minimal = True
    winecmd.arguments = ""
    winecmd.runner = "/runner/bin/wine"
    winecmd.gamescope_activated = False

    command = winecmd.get_cmd("game.exe")

    assert command == f"{entry_point}{separator}{winecmd.runner} game.exe"


def test_dedicated_sandbox_shares_forwarded_document_read_write(monkeypatch, tmp_path):
    bottle_path = tmp_path / "TestBottle"
    bottle_path.mkdir()
    document = "/run/user/1000/doc/abc123/My Document.txt"
    command_document = "/run/user/1000/doc/def456/Batch Document.txt"
    other_path = "/home/user/Other Document.txt"
    config = BottleConfig(Name="Test", Path=str(bottle_path), Runner="sys-wine")

    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_bottle_path",
        lambda _config: str(bottle_path),
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_runner_path",
        lambda _runner: "sys-wine",
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.resolve_portal_path",
        lambda path: path,
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.is_portal_document_path",
        lambda path: path in (document, command_document),
    )

    winecmd = WineCommand.__new__(WineCommand)
    winecmd.config = config
    winecmd.arguments = " ".join(shlex.quote(arg) for arg in (document, other_path))
    winecmd.command = "cmd /c {} {}".format(
        shlex.quote("C:\\probe.bat"),
        shlex.quote(command_document),
    )
    winecmd.cwd = str(bottle_path)
    winecmd.steam_runtime_root = None
    winecmd.env = {}

    sandbox = winecmd._get_sandbox_manager()

    assert document in sandbox.share_paths_rw
    assert command_document in sandbox.share_paths_rw
    assert other_path not in sandbox.share_paths_rw


def test_gamescope_reaper_stops_orphaned_descendant(monkeypatch, tmp_path):
    config = BottleConfig(Path=str(tmp_path))
    config.Parameters.gamescope = True
    config.Parameters.gamescope_fullscreen = False
    child_pid = tmp_path / "child.pid"
    runner = tmp_path / "runner"
    runner.write_text(
        "#!/bin/sh\nsleep 60 &\n"
        f"echo $! > {shlex.quote(str(child_pid))}\n"
        "exit 23\n"
    )
    runner.chmod(0o755)
    command = _gamescope_command(config, runner)
    monkeypatch.setattr(winecommand, "gamescope_available", "gamescope")
    monkeypatch.setattr(winecommand, "gamemode_available", False)
    monkeypatch.setattr(winecommand, "mangohud_available", False)
    monkeypatch.setattr(winecommand, "obs_vkc_available", False)
    arguments = shlex.split(command.get_cmd("app.exe"))
    launcher = arguments[arguments.index("--") + 1:]
    try:
        result = subprocess.run(launcher, timeout=5, check=False)
        assert result.returncode == 23
        pid = int(child_pid.read_text())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            pytest.fail("orphaned child remained after the game exited")
    finally:
        if child_pid.exists():
            try:
                os.kill(int(child_pid.read_text()), 9)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("path, parent", [
    ("C:/Game/game.exe", "C:/Game"),
    (r"C:\Game\game.exe", r"C:\Game"),
    ("C:/game.exe", "C:/"),
    ("/home/user/game.exe", "/home/user"),
])
def test_default_working_directory_uses_executable_parent(mocker, path, parent):
    from bottles.backend.wine.winepath import WinePath

    executor = WineExecutor.__new__(WineExecutor)
    executor.config = BottleConfig()
    executor._raw_exec_path = path
    convert = mocker.patch.object(WinePath, "to_unix", return_value="/converted")
    actual = executor._WineExecutor__get_cwd(None)
    if WinePath.is_windows(path):
        convert.assert_called_once_with(parent, native=True)
        assert actual == "/converted"
    else:
        convert.assert_not_called()
        assert actual == parent


@pytest.mark.parametrize("alias", ["USE", "ENABLE"])
def test_proton_variables_do_not_enable_native_wine_preferences(monkeypatch, alias):
    monkeypatch.setattr("bottles.backend.wine.winecommand.DisplayUtils.display_server_type", lambda: "wayland")
    env = WineEnv(clean=True)
    env.add("DISPLAY", ":1")
    env.add("WAYLAND_DISPLAY", "wayland-0")
    env.add(f"PROTON_{alias}_HDR", "1")
    env.add(f"PROTON_{alias}_WAYLAND", "1")
    apply_wayland_preferences(env, BottleParams())
    apply_hdr_preferences(env, BottleParams(), gamescope_activated=False)
    result = env.get()["envs"]
    assert result["DISPLAY"] == ":1"
    assert "DXVK_HDR" not in result
    assert "WINE_USE_EGL" not in result
    assert "WINEDLLOVERRIDES" not in result


def test_hidraw_setup_failure_stops_launch(monkeypatch, tmp_path):
    from bottles.backend.wine import executor as module
    config = BottleConfig(Name="Office", Path=str(tmp_path))
    config.Parameters.hidraw_devices = ["0x044F/0xB10A"]
    failure = Result(False, message="Registry import failed")
    calls = []
    monkeypatch.setattr(module, "configure_hidraw", lambda cfg, ids: calls.append((cfg, ids)) or failure)
    executor = WineExecutor.__new__(WineExecutor)
    executor.config = config
    executor._raw_exec_path = executor.exec_path = "C:/writer.exe"
    assert executor.run() is failure
    assert calls == [(config, ["0x044F/0xB10A"])]


def test_plain_wine_uses_newest_discovered_steam_runtime_with_spaces(monkeypatch, tmp_path):
    from bottles.backend.managers import steam as steam_module

    steam_path = tmp_path / "Steam Library"
    entries = (
        "steamapps/common/SteamLinuxRuntime_4/_v2-entry-point",
        "steamapps/common/SteamLinuxRuntime_sniper/_v2-entry-point",
        "steamapps/common/SteamLinuxRuntime_soldier/_v2-entry-point",
        "ubuntu12_32/steam-runtime/run.sh",
    )
    for relative in entries:
        path = steam_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(steam_module, "SteamManager", lambda check_only: SimpleNamespace(
        is_steam_supported=True, steam_path=str(steam_path),
    ))
    # Exercise discovery as well as command construction, not a hand-picked result.
    runtimes = winecommand.RuntimeManager._RuntimeManager__get_steam_runtime()
    assert list(runtimes) == ["steamrt4", "sniper", "soldier", "scout"]
    monkeypatch.setattr(winecommand.RuntimeManager, "get_runtimes", lambda _category: runtimes)

    command = WineCommand.__new__(WineCommand)
    command.config = BottleConfig(Runner="ordinary-wine")
    command.config.Parameters.use_steam_runtime = True
    command.runner = "/runner/bin/wine"
    command.arguments = ""
    command.minimal = True
    command.gamescope_activated = False
    expected_entry = steam_path / entries[0]
    assert shlex.split(command.get_cmd("application.exe")) == [
        str(expected_entry), "--", "/runner/bin/wine", "application.exe",
    ]
    assert command.steam_runtime_root == str(expected_entry.parent)


def _installer_executor(monkeypatch, exec_type, success_codes, returncode=0):
    """A WineExecutor whose installer exits with `returncode` on the Wine side."""
    if returncode:
        result = Result(False, message=f"Command exited with status {returncode}.")
    else:
        result = Result(True)

    class FakeWineCommand:
        def __init__(self, *_args, **_kwargs):
            self.returncode = None

        def run(self):
            self.returncode = returncode
            return result

    monkeypatch.setattr("bottles.backend.wine.wineprogram.WineCommand", FakeWineCommand)
    monkeypatch.setattr(
        WineExecutor,
        "_WineExecutor__set_monitors",
        lambda _self: None,
    )
    executor = WineExecutor.__new__(WineExecutor)
    executor.config = _make_config()
    executor.exec_type = exec_type
    executor.exec_path = "/tmp/bottles/setup." + exec_type
    executor.args = "/quiet"
    executor.terminal = False
    executor.environment = {}
    executor.pre_script = None
    executor.post_script = None
    executor.pre_script_args = None
    executor.post_script_args = None
    executor.cwd = None
    executor.hide_console = False
    executor.sandbox_override = None
    executor.success_codes = success_codes
    return executor


def _launch(executor):
    if executor.exec_type == "msi":
        return executor._WineExecutor__launch_msi()
    return executor._WineExecutor__launch_with_starter()


@pytest.mark.parametrize("exec_type", ["exe", "msi"])
@pytest.mark.parametrize(
    ("returncode", "ok"),
    [
        (0, True),
        # 3010 and 1641 as Wine reports them: one byte.
        (194, True),
        (105, True),
        (67, False),  # 1603, fatal error during installation
        (2, False),
        (1, False),
    ],
)
def test_installer_launch_follows_the_exit_status(
    monkeypatch, exec_type, returncode, ok
):
    executor = _installer_executor(monkeypatch, exec_type, [1641, 3010], returncode)

    result = _launch(executor)

    assert result.ok is ok
    assert result.data["returncode"] == returncode
    assert result.message == ("" if ok else f"Command exited with status {returncode}.")


@pytest.mark.parametrize("exec_type", ["exe", "msi"])
def test_launch_without_success_codes_still_ignores_the_exit_status(
    monkeypatch, exec_type
):
    executor = _installer_executor(monkeypatch, exec_type, None, 67)

    assert _launch(executor).ok


def test_installer_launch_failure_without_exit_status_is_kept(monkeypatch):
    # e.g. the "ShellExecuteEx" detection, which fails with an exit status of 0
    executor = _installer_executor(monkeypatch, "exe", [3010])
    monkeypatch.setattr(
        "bottles.backend.wine.wineprogram.WineCommand",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            run=lambda: Result(False, message="ShellExecuteEx exception"),
        ),
    )

    result = _launch(executor)

    assert not result.ok
    assert result.message == "ShellExecuteEx exception"


def test_executable_launch_accepts_configured_exit_status(monkeypatch):
    class Command:
        returncode = 194

        def __init__(self, *_args, **_kwargs):
            pass

        def run(self):
            return Result(False, message="Command exited with status 194.")

    monkeypatch.setattr("bottles.backend.wine.executor.WineCommand", Command)
    executor = _installer_executor(monkeypatch, "exe", [3010])
    executor.exec_path = "setup.exe"

    assert executor._WineExecutor__launch_exe().ok
    executor.success_codes = [0]
    assert not executor._WineExecutor__launch_exe().ok


@pytest.mark.parametrize(
    ("returncode", "codes", "expected"),
    [
        (None, [3010], False),
        (0, [0], False),
        (194, [3010], True),
        (3010, [3010], True),
        (102, [1638], True),
        (1, [3010], False),
        (194, [], False),
        (-62, [3010], False),
        (-151, [1641], False),
        (True, [1], False),
        (450, [3010], False),
        (194, [-62], False),
    ],
)
def test_is_success_exit_code(returncode, codes, expected):
    assert WineExecutor.is_success_exit_code(returncode, codes) is expected


@pytest.mark.parametrize("arch,version,expected", [
    ("win32", "winxp", "winxp"),
    ("win64", "winxp", "winxp64"),
    ("win64", "win7", "win7"),
])
def test_legacy_windows_version_uses_prefix_architecture(monkeypatch, arch, version, expected):
    from bottles.backend.wine import regkeys

    versions = []
    monkeypatch.setattr(regkeys, "WineCfg", lambda config: SimpleNamespace(
        set_windows_version=lambda value: versions.append(value) or Result(True),
    ))
    keys = regkeys.RegKeys.__new__(regkeys.RegKeys)
    keys.config = SimpleNamespace(Arch=arch)

    keys.lg_set_windows(version)

    assert versions == [expected]


@pytest.mark.parametrize("arch,expected", [("win32", "winxp"), ("win64", "winxp64")])
def test_windows_registry_values_match_prefix_architecture(monkeypatch, arch, expected):
    from bottles.backend.wine import regkeys

    bundles = []
    monkeypatch.setattr(regkeys, "WineBoot", lambda config: SimpleNamespace(
        restart=lambda: None, update=lambda: None,
    ))
    keys = regkeys.RegKeys.__new__(regkeys.RegKeys)
    keys.config = SimpleNamespace(Arch=arch)
    keys.reg = SimpleNamespace(remove=lambda *args: None, import_bundle=bundles.append)

    keys.set_windows("winxp")

    values = {item["value"]: item["data"] for item in bundles[0][
        "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows NT\\CurrentVersion"
    ]}
    assert values["CurrentVersion"] == regkeys.win_versions[expected]["CurrentVersion"]
    assert values["CSDVersion"] == regkeys.win_versions[expected]["CSDVersion"]


@pytest.mark.parametrize("status", [3, 4])
def test_wineboot_preserves_the_session_display(monkeypatch, status):
    from bottles.backend.wine.wineboot import WineBoot

    captured = {}
    monkeypatch.setenv("DISPLAY", ":17")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-fixture")
    def launch(self, **kwargs):
        env = winecommand.WineEnv()
        env.add_bundle(kwargs["environment"], override=True)
        captured.update(env.get()["envs"])
        return Result(True)

    monkeypatch.setattr(WineBoot, "launch", launch)

    assert WineBoot(_make_config()).send_status(status).ok
    assert captured["DISPLAY"] == ":17"
    assert captured["WAYLAND_DISPLAY"] == "wayland-fixture"



@pytest.mark.parametrize("runner_binary", ["/usr/bin/wine", "/runners/Wine with spaces/bin/wine64"])
def test_launch_scripts_receive_selected_wine_binary(monkeypatch, runner_binary):
    import shlex
    monkeypatch.setenv("WINE", "/incorrect/host/wine")
    command = WineCommand.__new__(WineCommand)
    command.config = _make_config()
    command.runner = shlex.quote(runner_binary)
    command.runner_runtime = ""
    command.steam_runtime_root = None
    command.minimal = True
    command.arguments = ""
    command.gamescope_activated = False
    command.terminal = False
    assert command.get_env()["WINE"] == runner_binary


@pytest.mark.parametrize("output,expected", [
    ("win11\n", "win11"), ("winxp64\n", "winxp64"),
    ("not a Windows version", None), (None, None),
])
def test_winecfg_reads_the_effective_windows_version(monkeypatch, output, expected):
    from bottles.backend.wine.winecfg import WineCfg

    calls = []
    def launch(_self, **kwargs):
        calls.append(kwargs)
        return Result(True, output)
    monkeypatch.setattr(WineCfg, "launch", launch)

    result = WineCfg(_make_config()).get_windows_version()

    assert result.ok is (expected is not None)
    if expected:
        assert result.data == expected
    assert calls == [{"args": "-v", "communicate": True, "action_name": "get_windows_version"}]
