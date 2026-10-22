# ruff: noqa: E402

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bottles.frontend.widgets import program


@pytest.mark.parametrize("sandbox", [False, True])
def test_stop_restores_buttons_after_worker(monkeypatch, iterate_until, sandbox):
    calls = []

    def kill_process(pid=None, name=None):
        calls.append((pid, name))

    monkeypatch.setattr(
        program, "WineDbg", lambda config: SimpleNamespace(kill_process=kill_process)
    )
    monkeypatch.setattr(
        program,
        "WineServer",
        lambda config: SimpleNamespace(force_kill=lambda: calls.append("sandbox")),
    )
    run, stop = Gtk.Button(), Gtk.Button()
    run.set_visible(False)
    stop.set_visible(True)
    entry = SimpleNamespace(
        config=SimpleNamespace(Parameters=SimpleNamespace(sandbox=sandbox)),
        program={"name": "Fixture"},
        executable="fixture.exe",
        window=SimpleNamespace(show_toast=Mock()),
        btn_run=run,
        btn_stop=stop,
    )
    entry._ProgramEntry__reset_buttons = (
        lambda result, error: program.ProgramEntry._ProgramEntry__reset_buttons(
            entry, result, error
        )
    )
    program.ProgramEntry.stop_process(entry, stop)
    iterate_until(run.get_visible)
    assert calls == (["sandbox"] if sandbox else [(None, "fixture.exe")])
    assert run.get_visible() and run.get_sensitive()
    assert not stop.get_visible() and not stop.get_sensitive()
