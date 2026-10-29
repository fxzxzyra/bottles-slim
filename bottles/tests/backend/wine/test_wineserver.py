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


def test_status_check_reaps_a_running_probe(mocker, tmp_path, runner_factory):
    import subprocess
    info = runner_factory("probe")
    config = BottleConfig(Path=str(tmp_path), Runner=info.identifier)
    probe = mocker.Mock()
    probe.wait.side_effect = [subprocess.TimeoutExpired(info.wineserver, 0.5), 0]
    mocker.patch("bottles.backend.wine.wineserver.subprocess.Popen", return_value=probe)
    assert WineServer(config).is_alive()
    assert probe.wait.call_args_list == [mocker.call(timeout=0.5), mocker.call()]
    probe.kill.assert_called_once_with()


def test_status_check_returns_immediately_for_a_finished_probe(mocker, tmp_path, runner_factory):
    info = runner_factory("finished")
    config = BottleConfig(Path=str(tmp_path), Runner=info.identifier)
    probe = mocker.Mock()
    probe.wait.return_value = 0
    mocker.patch("bottles.backend.wine.wineserver.subprocess.Popen", return_value=probe)
    assert not WineServer(config).is_alive()
    probe.wait.assert_called_once_with(timeout=0.5)
    probe.kill.assert_not_called()
