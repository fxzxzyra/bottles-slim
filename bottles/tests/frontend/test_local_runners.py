from types import SimpleNamespace

from gi.repository import Adw

from bottles.backend.utils.runners import RunnerRegistry
from bottles.frontend.views.preferences import PreferencesWindow


def test_local_runner_groups_work_without_network(runner_factory):
    Adw.init()
    system = runner_factory("system-wine", "system")
    user = runner_factory("custom-wine")
    registrations = {user.identifier: user.root}
    view = SimpleNamespace(
        system_runners=Adw.PreferencesGroup(),
        user_runners=Adw.PreferencesGroup(),
        manager=SimpleNamespace(data_mgr=SimpleNamespace(get=lambda key: registrations)),
        _PreferencesWindow__runner_rows=[],
        _PreferencesWindow__forget_user_runner=lambda *_args: None,
    )

    PreferencesWindow.populate_runners_list(view)

    rows = view._PreferencesWindow__runner_rows
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
        _PreferencesWindow__runner_rows=[],
    )

    PreferencesWindow.populate_runners_list(view)

    assert len(view._PreferencesWindow__runner_rows) == 1
    group, row = view._PreferencesWindow__runner_rows[0]
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
