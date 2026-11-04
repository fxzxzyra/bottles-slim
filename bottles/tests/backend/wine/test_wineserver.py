import subprocess

import pytest

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
    popen.return_value.wait.return_value = 0
    server = WineServer(config)
    assert server.wait() == 0
    server.kill()
    assert [call.args[0] for call in popen.call_args_list] == [
        [info.wineserver, "-w"], [info.wineserver, "-k"],
    ]
    assert popen.call_args.kwargs["env"]["WINEPREFIX"] == str(tmp_path)
    assert server.returncode == 0


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


@pytest.mark.parametrize("argument", ["-k", "-w"])
def test_stop_reaps_timed_out_native_server(mocker, argument):
    config = BottleConfig(Name="Test", Runner="soda-test")
    process = mocker.Mock()
    process.wait.side_effect = [subprocess.TimeoutExpired("wineserver", 30), 0]
    run = mocker.patch.object(WineServer, "_run", return_value=process)
    server = WineServer(config)
    if argument == "-w":
        mocker.patch.object(server, "kill", side_effect=lambda **_kw: setattr(server, "returncode", 0))

    with pytest.raises(subprocess.TimeoutExpired):
        server.stop()

    run.assert_called_once_with([argument])
    process.kill.assert_called_once_with()
    assert process.wait.call_args_list == [mocker.call(timeout=30), mocker.call()]



@pytest.mark.parametrize("codes,expected", [([0, 0], True), ([1], False), ([0, 1], False)])
def test_stop_checks_native_server_status(mocker, codes, expected):
    config = BottleConfig(Name="Test", Runner="soda-test")
    process = mocker.Mock()
    process.wait.side_effect = codes
    run = mocker.patch.object(WineServer, "_run", return_value=process)

    assert WineServer(config).stop() is expected

    assert run.call_args_list == [mocker.call([arg]) for arg in ["-k", "-w"][:len(codes)]]



def test_stop_uses_tracked_sandbox_only(monkeypatch, mocker, tmp_path):
    config = BottleConfig(Name="Test", Runner="soda-test")
    config.Parameters.sandbox = True
    monkeypatch.setattr("bottles.backend.wine.wineserver.ManagerUtils.get_bottle_path", lambda _config: str(tmp_path))
    terminate = mocker.patch("bottles.backend.managers.sandbox.SandboxManager.terminate_prefix")
    run = mocker.patch.object(WineServer, "_run")

    assert WineServer(config).stop() is True

    terminate.assert_called_once_with(str(tmp_path), timeout=30)
    run.assert_not_called()
