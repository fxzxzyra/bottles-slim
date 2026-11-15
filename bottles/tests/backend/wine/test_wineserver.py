from bottles.backend.models.config import BottleConfig
from bottles.backend.wine.wineserver import WineServer


def test_is_alive_skips_missing_bottle_directory(monkeypatch, mocker, tmp_path):
    config = BottleConfig(Path=str(tmp_path / "missing"), Runner="system-wine")
    popen = mocker.patch("bottles.backend.wine.wineserver.subprocess.Popen")
    assert WineServer(config).is_alive() is False
    popen.assert_not_called()


def test_is_alive_handles_bottle_removed_during_check(monkeypatch, mocker, tmp_path, runner_factory):
    info = runner_factory("system-wine", "system")
    config = BottleConfig(Path=str(tmp_path), Runner=info.identifier)
    popen = mocker.patch(
        "bottles.backend.wine.wineserver.subprocess.Popen", side_effect=FileNotFoundError,
    )
    assert WineServer(config).is_alive() is False
    assert popen.call_args.args[0] == [info.wineserver, "-w"]


def test_wait_and_kill_use_the_selected_server(mocker, tmp_path, runner_factory):
    info = runner_factory("custom")
    config = BottleConfig(Path=str(tmp_path), Runner=info.identifier)
    popen = mocker.patch("bottles.backend.wine.wineserver.subprocess.Popen")
    run = mocker.patch("bottles.backend.wine.wineserver.subprocess.run")
    server = WineServer(config)
    server.wait()
    server.kill()
    assert popen.call_args.args[0] == [info.wineserver, "-w"]
    assert popen.call_args.kwargs["env"]["WINEPREFIX"] == str(tmp_path)
    assert run.call_args.args[0] == [info.wineserver, "-k"]
