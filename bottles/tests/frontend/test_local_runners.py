from types import SimpleNamespace

from gi.repository import Adw

from bottles.backend.utils.runners import RunnerRegistry
from bottles.frontend.views.preferences import PreferencesDialog


def test_local_runner_groups_work_without_network(runner_factory):
    Adw.init()
    system = runner_factory("system-wine", "system")
    user = runner_factory("custom-wine")
    registrations = {user.identifier: {"name": "custom-wine", "path": user.root}}
    view = SimpleNamespace(
        system_runners=Adw.PreferencesGroup(),
        user_runners=Adw.PreferencesGroup(),
        manager=SimpleNamespace(data_mgr=SimpleNamespace(get=lambda key: registrations)),
        _PreferencesDialog__runner_rows=[],
        _PreferencesDialog__forget_user_runner=lambda *_args: None,
        _PreferencesDialog__edit_user_runner=lambda *_args: None,
    )

    PreferencesDialog.populate_runners_list(view)

    rows = view._PreferencesDialog__runner_rows
    assert len(rows) == 2
    assert rows[0][0] is view.system_runners
    assert rows[1][0] is view.user_runners
    assert rows[0][1].get_subtitle() == system.root
    assert rows[1][1].get_subtitle() == user.root


def test_missing_system_runner_keeps_install_guidance_visible(monkeypatch):
    Adw.init()
    monkeypatch.setattr(RunnerRegistry, "entries", {})
    view = SimpleNamespace(
        system_runners=Adw.PreferencesGroup(),
        user_runners=Adw.PreferencesGroup(),
        manager=SimpleNamespace(data_mgr=SimpleNamespace(get=lambda key: {})),
        _PreferencesDialog__runner_rows=[],
    )

    PreferencesDialog.populate_runners_list(view)

    assert len(view._PreferencesDialog__runner_rows) == 1
    group, row = view._PreferencesDialog__runner_rows[0]
    assert group is view.system_runners
    assert row.get_title() == "System Wine is unavailable"
    assert row.get_subtitle()


def test_missing_runner_selection_does_not_rewrite_config():
    from unittest.mock import Mock
    from gi.repository import Gtk
    from bottles.backend.models.config import BottleConfig
    from bottles.frontend.views.bottle_preferences import PreferencesView

    config = BottleConfig(Runner="missing")
    view = SimpleNamespace(
        config=config, _runner_ids=["system-wine"], combo_runner=Mock(),
    )
    PreferencesView._PreferencesView__select_configured_runner(view)
    view.combo_runner.set_selected.assert_called_once_with(Gtk.INVALID_LIST_POSITION)
    assert config.Runner == "missing"


def test_unavailable_user_runner_keeps_its_name_path_and_edit_action(monkeypatch):
    from gi.repository import Gtk

    monkeypatch.setattr(RunnerRegistry, "entries", {})
    registration = {"user-id": {"name": "Office Wine", "path": "/opt/user/Wine"}}
    edits = []
    view = SimpleNamespace(
        system_runners=Adw.PreferencesGroup(), user_runners=Adw.PreferencesGroup(),
        manager=SimpleNamespace(data_mgr=SimpleNamespace(get=lambda _key: registration)),
        _PreferencesDialog__runner_rows=[],
        _PreferencesDialog__edit_user_runner=lambda _button, identifier: edits.append(identifier),
        _PreferencesDialog__forget_user_runner=lambda *_args: None,
    )
    PreferencesDialog.populate_runners_list(view)
    rows = [row for group, row in view._PreferencesDialog__runner_rows if group is view.user_runners]
    assert len(rows) == 1
    row = rows[0]
    assert row.get_title() == "Office Wine"
    assert "/opt/user/Wine" in row.get_subtitle()
    def buttons(widget):
        child = widget.get_first_child()
        while child:
            if isinstance(child, Gtk.Button):
                yield child
            yield from buttons(child)
            child = child.get_next_sibling()
    edit = next(button for button in buttons(row) if button.get_icon_name() == "document-edit-symbolic")
    edit.emit("clicked")
    assert edits == ["user-id"]


def test_runner_registration_form_requires_name_and_directory(monkeypatch):
    from gi.repository import Gtk
    from bottles.backend.models.result import Result

    opened, saved, refreshes = [], [], []
    view = Adw.Bin()
    view.manager = SimpleNamespace(
        data_mgr=SimpleNamespace(get=lambda _key: {}),
        register_user_runner=lambda *args: saved.append(args) or Result(True),
    )
    view.populate_runners_list = lambda: refreshes.append(True)
    monkeypatch.setattr(Adw.AlertDialog, "present", lambda dialog, _parent: opened.append(dialog))
    PreferencesDialog._PreferencesDialog__runner_registration(view)
    dialog = opened[0]
    assert not dialog.get_response_enabled("save")
    def entries(widget):
        child = widget.get_first_child()
        while child:
            if isinstance(child, Adw.EntryRow):
                yield child
            yield from entries(child)
            child = child.get_next_sibling()
    fields = {entry.get_title(): entry for entry in entries(dialog.get_extra_child())}
    fields["Name"].set_text("Office Wine")
    assert not dialog.get_response_enabled("save")
    fields["Directory"].set_text("/opt/user/Wine")
    assert dialog.get_response_enabled("save")
    dialog.emit("response", "save")
    assert saved == [("Office Wine", "/opt/user/Wine", None)]
    assert refreshes == [True]
