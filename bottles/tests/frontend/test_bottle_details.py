# ruff: noqa: E402

from dataclasses import replace
from types import SimpleNamespace

import pytest
from gi.repository import Gtk

from bottles.backend.utils.runners import RunnerRegistry


from bottles.backend.models.config import BottleConfig
from bottles.frontend.views import bottle_details
from bottles.frontend.views.bottle_details import BottleView


class WidgetStub:
    def __init__(self):
        self.text = None

    def set_text(self, text):
        self.text = text

    def set_tooltip_text(self, _text):
        pass

    def set_visible(self, _visible):
        pass


@pytest.mark.parametrize("flatpak", [False, True])
@pytest.mark.parametrize("source, expected", [
    ("system", "System · wine-11.0 (wine-11.1)"),
    ("user", "User · wine-11.0 (wine-11.1)"),
])
def test_runner_label_uses_registered_source_and_version(
    monkeypatch, runner_factory, flatpak, source, expected,
):
    info = runner_factory("wine-11.0", source)
    RunnerRegistry.entries[info.identifier] = replace(info, version="wine-11.1")
    runner_label = Gtk.Label()
    widget = WidgetStub()
    config = BottleConfig(
        Name="Test",
        Runner=info.identifier,
        Environment="Gaming",
        Update_Date="2026-01-01 00:00:00.000000",
    )
    view = SimpleNamespace(
        manager=SimpleNamespace(
            runners_available=[info.identifier],
            versioning_manager=SimpleNamespace(needs_migration=lambda _config: False),
        ),
        label_name=widget,
        label_arch=widget,
        label_runner=runner_label,
        label_environment=widget,
        versioning_badge=widget,
        label_state=widget,
        _BottleView__update_by_env=lambda: None,
        update_programs=lambda: None,
        populate_updates=lambda: None,
    )
    if flatpak:
        monkeypatch.setenv("FLATPAK_ID", "com.usebottles.bottles")
    else:
        monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(
        bottle_details.ManagerUtils,
        "get_bottle_path",
        lambda _config: "/tmp/test-bottle",
    )
    monkeypatch.setattr(bottle_details.os.path, "exists", lambda _path: False)

    BottleView.set_config(view, config)

    assert runner_label.get_text() == expected
    assert config.Runner == info.identifier


def test_missing_runner_dialog_waits_for_versioning_upgrade(monkeypatch):
    events = []
    callbacks = []
    widget = WidgetStub()
    config = BottleConfig(
        Name="Test",
        Runner="missing-runner",
        Environment="Gaming",
        Update_Date="2026-01-01 00:00:00.000000",
        Versioning=True,
    )

    def show_upgrade(on_close=None):
        events.append("upgrade")
        callbacks.append(on_close)

    view = SimpleNamespace(
        manager=SimpleNamespace(
            runners_available=[],
            versioning_manager=SimpleNamespace(needs_migration=lambda _config: True),
        ),
        label_name=widget,
        label_arch=widget,
        label_runner=widget,
        label_environment=widget,
        versioning_badge=widget,
        label_state=widget,
        _BottleView__update_by_env=lambda: None,
        _BottleView__upgrade_versioning=show_upgrade,
        _BottleView__alert_missing_runner=lambda: events.append("missing-runner"),
        update_programs=lambda: None,
        populate_updates=lambda: None,
    )

    monkeypatch.setattr(
        bottle_details.ManagerUtils,
        "get_bottle_path",
        lambda _config: "/tmp/test-bottle",
    )
    monkeypatch.setattr(bottle_details.os.path, "exists", lambda _path: False)

    BottleView.set_config(view, config)

    assert events == ["upgrade"]
    assert callbacks[0] is not None

    callbacks[0]()

    assert events == ["upgrade", "missing-runner"]


def test_versioning_upgrade_schedules_follow_up_after_close(monkeypatch):
    events = []
    connections = []

    class DialogStub:
        def connect(self, signal, callback):
            events.append("connect")
            connections.append((signal, callback))

        def present(self):
            events.append("present")

    dialog = DialogStub()
    monkeypatch.setattr(
        bottle_details,
        "UpgradeVersioningDialog",
        lambda _parent: dialog,
    )
    monkeypatch.setattr(
        bottle_details.GLib,
        "idle_add",
        lambda callback: events.append("scheduled") or callback(),
    )

    BottleView._BottleView__upgrade_versioning(
        SimpleNamespace(),
        lambda: events.append("missing-runner"),
    )

    assert events == ["connect", "present"]
    assert connections[0][0] == "close-request"

    assert connections[0][1](dialog) is False
    assert events == ["connect", "present", "scheduled", "missing-runner"]


@pytest.mark.parametrize("force_update", [False, True])
def test_update_programs_controls_cache_refresh(monkeypatch, force_update):
    calls = []
    config = BottleConfig(Name="Test")
    manager = SimpleNamespace(
        get_programs=lambda _config, **kwargs: calls.append(kwargs) or []
    )
    view = SimpleNamespace(
        config=config,
        manager=manager,
        empty_list=lambda: None,
        row_no_programs=SimpleNamespace(set_visible=lambda _visible: None),
        show_hidden=False,
    )

    monkeypatch.setattr(bottle_details.GLib, "idle_add", lambda *_args: None)
    monkeypatch.setattr(
        bottle_details,
        "WineServer",
        lambda _config: SimpleNamespace(is_alive=lambda: False),
    )

    BottleView.update_programs(view, force_update=force_update)

    assert calls == [{"force_update": force_update}]


def test_populate_updates_hides_empty_group():
    visibility = []
    view = SimpleNamespace(
        config=BottleConfig(Name="Test"),
        manager=SimpleNamespace(
            settings=SimpleNamespace(get_boolean=lambda _key: True),
            get_component_updates=lambda _config: [],
        ),
        group_updates=SimpleNamespace(
            remove=lambda _row: None,
            set_visible=visibility.append,
        ),
        _BottleView__update_rows=[],
    )

    BottleView.populate_updates(view)

    assert visibility == [False]


def test_backup_progress_matches_uuid_and_kind_instead_of_title(monkeypatch):
    from bottles.backend.state import Task, TaskManager, SignalManager
    from bottles.backend.models.result import Result
    from bottles.frontend.views.bottle_details import BottleView
    config = BottleConfig(Name="Renamed")
    visible = []
    page = SimpleNamespace(config=config, _show_backup_progress=lambda: visible.append(True))
    monkeypatch.setattr(TaskManager, "_TASKS", {})
    monkeypatch.setattr(SignalManager, "_SIGNALS", {})
    monkeypatch.setattr("bottles.frontend.views.bottle_details.GLib.idle_add", lambda callback: callback())
    other = Task(title='Backup Renamed', kind="backup", bottle_id="other")
    own = Task(title='An old translated title', kind="backup", bottle_id=config.Id)
    other_id, own_id = TaskManager.add(other), TaskManager.add(own)
    BottleView._on_task_added(page, Result(True, other_id))
    assert visible == []
    BottleView._on_task_added(page, Result(True, own_id))
    assert visible == [True]
    assert page._backup_task_id == own_id
