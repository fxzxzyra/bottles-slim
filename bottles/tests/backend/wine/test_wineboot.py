from bottles.backend.models.config import BottleConfig
from bottles.backend.wine.wineboot import WineBoot
from bottles.backend.wine.winecommand import WineCommand


def test_wineboot_disables_unmanaged_mono(monkeypatch):
    launches = []

    class FakeWineCommand:
        def __init__(self, _config, **kwargs):
            launches.append(kwargs)

        def run(self):
            return None

    monkeypatch.setattr(
        "bottles.backend.wine.wineprogram.WineCommand",
        FakeWineCommand,
    )
    monkeypatch.setattr(
        "bottles.backend.wine.wineboot.WineServer.is_alive", lambda _self: True
    )
    wineboot = WineBoot(BottleConfig())

    wineboot.init()
    wineboot.update()
    wineboot.restart()
    wineboot.shutdown()
    wineboot.send_status(11)
    wineboot.send_status(12)
    wineboot.force()
    wineboot.kill()

    assert [launch["command"] for launch in launches] == [
        "wineboot -i /nogui",
        "wineboot -u /nogui",
        "wineboot -r /nogui",
        "wineboot -s /nogui",
        "wineboot -e -f -k -r /nogui",
        "wineboot -e -f -k -s /nogui",
        "wineboot force /nogui",
        "wineboot -k /nogui",
    ]
    assert [launch.get("forced_dll_overrides") for launch in launches] == [
        "mscoree=d",
        "mscoree=d",
        None,
        None,
        None,
        None,
        None,
        None,
    ]
    assert all(
        launch["environment"]["WINEDLLOVERRIDES"] == "winemenubuilder=d"
        for launch in launches
    )


def test_forced_dll_overrides_take_precedence(monkeypatch, tmp_path, runner_factory):
    runner_factory("sys-wine")
    config = BottleConfig(
        Path=str(tmp_path),
        Runner="sys-wine",
        DLL_Overrides={"mscoree": "n,b"},
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_bottle_path",
        lambda _config: str(tmp_path),
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.ManagerUtils.get_runner_path",
        lambda _runner: "sys-wine",
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.DisplayUtils.check_nvidia_device",
        lambda: None,
    )
    monkeypatch.setattr(
        "bottles.backend.wine.winecommand.GPUUtils.get_gpu",
        lambda _self: {"prime": {"discrete": None, "integrated": None}, "vendors": {}},
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
    winecmd.forced_dll_overrides = "mscoree=d"

    env = winecmd.get_env()

    assert env["WINEDLLOVERRIDES"].split(";")[-1] == "mscoree=d"
    assert config.DLL_Overrides == {"mscoree": "n,b"}


def test_native_stop_matches_exact_bottle_uuid(monkeypatch):
    import io
    import signal
    from bottles.backend.wine import wineboot as module
    config = BottleConfig(Name="Office", Path="/prefix")
    boot = object.__new__(WineBoot)
    boot.config = config
    environments = {
        "/proc/10/environ": b"BOTTLE=/prefix\0BOTTLE_ID=" + config.Id.encode() + b"\0",
        "/proc/11/environ": b"BOTTLE=/prefix\0BOTTLE_ID=" + config.Id.encode() + b"extra\0",
        "/proc/12/environ": b"BOTTLE=/prefix\0BOTTLE_ID=other\0",
    }
    monkeypatch.setattr(module.os, "listdir", lambda _path: ["10", "11", "12"])
    monkeypatch.setattr("builtins.open", lambda path, mode: io.BytesIO(environments[path]))
    killed = []
    monkeypatch.setattr(module.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    boot.nv_stop_all_processes()
    assert killed == [(10, signal.SIGTERM)]
