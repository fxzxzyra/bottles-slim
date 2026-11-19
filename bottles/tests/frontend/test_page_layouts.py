"""Exercise compiled page templates and the state transitions visible to users."""

from types import SimpleNamespace

import pytest
from gi.repository import Adw, Gio, Gtk

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.state import SignalManager
from bottles.frontend.views import bottle_details, importer


@pytest.fixture
def details_pages(monkeypatch):
    monkeypatch.setattr(SignalManager, "_SIGNALS", {})
    # Catalog queries are unrelated to template construction or drag delivery.
    monkeypatch.setattr(bottle_details.BottleView, "populate_updates", lambda _self: None)
    details = SimpleNamespace(
        window=SimpleNamespace(manager=object()), stack_bottle=Gtk.Stack(),
    )
    return [bottle_details.BottleView(details, BottleConfig(Name=name))
            for name in ("Office", "Game")]


def test_details_content_and_drop_prompt_are_attached(details_pages):
    view = details_pages[0]
    overlay = view.get_child()
    page = overlay.get_child()
    assert isinstance(overlay, Gtk.Overlay)
    assert isinstance(page, Adw.PreferencesPage)
    assert view.label_name.is_ancestor(page)
    assert view.btn_execute.is_ancestor(page)
    assert view.drop_overlay.get_parent() is overlay
    assert not view.drop_overlay.get_can_target()
    assert not view.drop_overlay.get_visible()
    view.target.emit("enter", 0.0, 0.0)
    assert view.drop_overlay.get_visible()
    view.target.emit("leave")
    assert not view.drop_overlay.get_visible()


def test_details_pages_own_independent_drop_controllers(details_pages):
    first, second = details_pages
    assert first.target is not second.target
    assert first.target.get_widget() is first
    assert second.target.get_widget() is second
    second.target.emit("enter", 0.0, 0.0)
    assert second.drop_overlay.get_visible()
    assert not first.drop_overlay.get_visible()
    second.target.emit("leave")


def test_details_program_lists_are_independent(details_pages):
    first, second = details_pages
    assert first._BottleView__registry is not second._BottleView__registry
    row = Adw.ActionRow(title="Office")
    first.add_program(row)
    second.empty_list()
    assert row.is_ancestor(first.group_programs)
    first.empty_list()
    assert row.get_parent() is None


def test_empty_drop_is_rejected(details_pages):
    view = details_pages[0]
    assert view.on_drop(view.target, SimpleNamespace(get_files=lambda: []), 0, 0) is False


@pytest.mark.parametrize("filename, accepted", [("Program.EXE", True), ("Setup.MSI", True), ("Program.exe.bak", False)])
def test_drop_checks_the_actual_extension(details_pages, monkeypatch, filename, accepted):
    view = details_pages[0]
    launches, messages = [], []
    view.window.show_toast = messages.append
    monkeypatch.setattr(bottle_details, "guard_sandbox_launch",
                        lambda _window, _config, path, _proceed: launches.append(path))
    file = Gio.File.new_for_path("/tmp/" + filename)
    assert view.on_drop(view.target, SimpleNamespace(get_files=lambda: [file]), 0, 0) is accepted
    assert launches == ([file.get_path()] if accepted else [])
    assert bool(messages) is not accepted


@pytest.fixture
def import_page(monkeypatch):
    monkeypatch.setattr(SignalManager, "_SIGNALS", {})
    callbacks, messages = [], []
    manager = SimpleNamespace(import_manager=SimpleNamespace())
    updates = []
    window = SimpleNamespace(
        manager=manager, show_toast=messages.append, refreshes=updates,
        page_list=SimpleNamespace(update_bottles_list=lambda: updates.append(True)),
    )
    monkeypatch.setattr(importer, "RunAsync",
                        lambda _func, callback, **_kwargs: callbacks.append(callback))
    return importer.ImporterView(window), callbacks, messages


def test_import_exception_reports_failure(import_page, iterate_until):
    view, _callbacks, messages = import_page
    view._ImporterView__finish(None, RuntimeError("Cannot read configuration"))
    iterate_until(lambda: bool(messages))
    assert messages == ["Cannot read configuration"]


def test_successful_registration_refreshes_the_container_list(import_page, iterate_until):
    view, _callbacks, messages = import_page
    view._ImporterView__finish(Result(True))
    iterate_until(lambda: bool(messages))
    assert messages == [importer._("Container imported successfully")]
    assert view.window.refreshes == [True]


def _descendants(widget):
    child = widget.get_first_child()
    while child:
        yield child
        yield from _descendants(child)
        child = child.get_next_sibling()


def test_importer_actions_share_one_scroll_area(import_page):
    view, callbacks, _messages = import_page
    assert sum(isinstance(w, Gtk.ScrolledWindow) for w in _descendants(view)) == 1
    assert not any(isinstance(w, Adw.StatusPage) for w in _descendants(view))
    assert view.btn_import_existing.is_ancestor(view)
    assert view.btn_import_config.get_parent() is not None
    assert view.btn_import_full.get_parent() is not None
    assert callbacks == []


@pytest.mark.parametrize("full, name", [(True, "tar.gz"), (False, "YAML")])
def test_backup_choices_use_the_same_file_dialog_flow(import_page, monkeypatch, tmp_path, full, name):
    from gi.repository import Gio
    view, _callbacks, _messages = import_page
    opened, restored = [], []
    selected = tmp_path / ("backup.tar.gz" if full else "backup.yml")
    monkeypatch.setattr(Gtk.FileDialog, "open", lambda dialog, parent, cancellable, callback: opened.append((dialog, callback)))
    monkeypatch.setattr(Gtk.FileDialog, "open_finish", lambda *_args: Gio.File.new_for_path(str(selected)))
    monkeypatch.setattr(view, "_ImporterView__restore_backup", lambda *args: restored.append(args))
    if full:
        view._ImporterView__import_full_bck()
    else:
        view._ImporterView__import_config_bck()
    dialog, callback = opened.pop()
    assert isinstance(dialog, Gtk.FileDialog)
    assert dialog.get_filters().get_n_items() == 2
    assert dialog.get_filters().get_item(0).get_name() == name
    assert dialog.get_accept_label() == importer._("Import")
    callback(dialog, object())
    assert restored == [("full" if full else "config", str(selected))]


def test_details_status_badges_fit_long_names_without_becoming_navigation(details_pages):
    from gi.repository import Pango

    view = details_pages[0]
    view.label_runner.set_text("Locally built Wine with a very long runner name " * 4)
    view.label_state.set_text("Long snapshot branch " * 6)
    assert isinstance(view.versioning_badge, Gtk.Box)
    assert view.label_runner.get_ellipsize() == Pango.EllipsizeMode.MIDDLE
    assert view.label_runner.get_tooltip_text() == view.label_runner.get_text()
    assert view.label_state.get_tooltip_text() == view.label_state.get_text()
    badges = view.label_runner.get_parent().get_parent()
    assert isinstance(badges, Adw.WrapBox)
    minimum_width, *_rest = badges.measure(Gtk.Orientation.HORIZONTAL, -1)
    assert minimum_width <= 360
