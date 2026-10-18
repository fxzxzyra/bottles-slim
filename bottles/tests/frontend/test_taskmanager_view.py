"""Real selection/list models, with only Wine queries and scheduling controlled."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from gi.repository import Gtk

from bottles.backend.models.config import BottleConfig
from bottles.frontend.views import bottle_taskmanager as module


@pytest.fixture
def task_page(monkeypatch):
    jobs = []
    bridge = Mock()
    bridge.is_available.return_value = True
    bridge.get_procs.return_value = [
        {"pid": "10", "name": "editor.exe", "threads": "2"},
        {"pid": "11", "name": "viewer.exe", "threads": "1"},
    ]
    monkeypatch.setattr(module, "WineBridge", lambda _config: bridge)
    monkeypatch.setattr(module, "RunAsync", lambda task, callback: jobs.append((task, callback)))
    view = module.TaskManagerView(
        SimpleNamespace(window=SimpleNamespace(manager=object())), BottleConfig(Runner="local"),
    )
    return view, jobs, bridge


def complete(job):
    task, callback = job
    callback(task(), None)


def test_process_table_selection_and_stop_use_the_selected_pid(task_page):
    view, jobs, bridge = task_page
    assert isinstance(view.processes_view, Gtk.ColumnView)
    assert not view.btn_kill.get_sensitive()
    complete(jobs.pop(0))
    assert [view.processes.get_item(i).values for i in range(2)] == [
        ("10", "editor.exe", "2"), ("11", "viewer.exe", "1"),
    ]
    assert not view.btn_kill.get_sensitive()  # Loading must not auto-select a process.
    view.selection.set_selected(1)
    assert view.btn_kill.get_sensitive()
    view.btn_kill.emit("clicked")
    complete(jobs.pop(0))
    bridge.kill_proc.assert_called_once_with(pid="11")
    # Stop completion reloads the actual process list instead of hiding a row.
    bridge.get_procs.return_value = [{"pid": "10", "name": "editor.exe"}]
    complete(jobs.pop(0))
    assert view.processes.get_n_items() == 1
    assert view.processes.get_item(0).values == ("10", "editor.exe", "0")


def test_refresh_ignores_stale_bottle_and_recovers_from_error(task_page):
    view, jobs, _bridge = task_page
    stale = jobs.pop(0)
    view.set_config(BottleConfig(Name="Other", Runner="another"))
    view.update()
    current = jobs.pop(0)
    stale[1]([{"pid": "1", "name": "wrong-bottle"}], None)
    assert view.processes.get_n_items() == 0
    assert not view.btn_update.get_sensitive()
    current[1](None, RuntimeError("Wine query failed"))
    assert view.processes.get_n_items() == 0
    assert view.btn_update.get_sensitive()
    assert not view.btn_kill.get_sensitive()
    view.kill_process()
    assert jobs == []  # No selection means no Wine command.


def test_stop_failure_does_not_hide_a_running_program(task_page):
    view, jobs, _bridge = task_page
    complete(jobs.pop(0))
    view.selection.set_selected(0)
    view.kill_process()
    jobs.pop(0)[1](None, RuntimeError("access denied"))
    complete(jobs.pop(0))
    assert [view.processes.get_item(i).values[0] for i in range(2)] == ["10", "11"]


def test_winedbg_fallback_uses_same_model_and_pid(task_page, monkeypatch):
    view, jobs, bridge = task_page
    bridge.is_available.return_value = False
    debugger = Mock()
    debugger.get_processes.return_value = [{"pid": "00ab", "name": "notepad.exe"}]
    monkeypatch.setattr(module, "WineDbg", lambda _config: debugger)
    complete(jobs.pop(0))
    view.selection.set_selected(0)
    view.kill_process()
    complete(jobs.pop(0))
    debugger.kill_process.assert_called_once_with(pid="00ab")
    bridge.kill_proc.assert_not_called()


def test_process_columns_render_model_values(task_page, iterate_until, widget_texts):
    view, jobs, _bridge = task_page
    parent = Gtk.Window(default_width=600, default_height=300)
    parent.set_child(view)
    complete(jobs.pop(0))
    parent.present()
    try:
        iterate_until(lambda: "viewer.exe" in widget_texts(view))
        labels = widget_texts(view)
        assert {"PID", "Name", "Threads", "10", "11", "editor.exe", "viewer.exe"}.issubset(labels)
    finally:
        parent.destroy()
