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
    manager = SimpleNamespace(import_manager=SimpleNamespace(search_wineprefixes=object()))
    window = SimpleNamespace(manager=manager, show_toast=messages.append)
    monkeypatch.setattr(importer, "RunAsync",
                        lambda _func, callback, **_kwargs: callbacks.append(callback))
    return importer.ImporterView(window), callbacks, messages


def test_prefix_refresh_replaces_results_with_empty_page(import_page, iterate_until):
    view, callbacks, messages = import_page
    assert view.stack_prefixes.get_visible_child_name() == "empty"
    assert view.status_page.get_parent() is view.stack_prefixes
    view._ImporterView__search_prefixes(view.btn_find_prefixes)
    assert not view.btn_find_prefixes.get_sensitive()
    assert not view.btn_select_prefixes.get_sensitive()
    assert view.stack_prefixes.get_visible_child_name() == "searching"
    callbacks.pop()(Result(True, {"wineprefixes": [
        {"Name": "Office", "Manager": "Wine", "Path": "/opt/user/Office", "Lock": False},
    ]}), None)
    iterate_until(lambda: view.btn_find_prefixes.get_sensitive())
    assert view.stack_prefixes.get_visible_child_name() == "prefixes"
    assert view.list_prefixes.get_first_child().get_title() == "Office"
    view._ImporterView__search_prefixes(view.btn_find_prefixes)
    callbacks.pop()(Result(True, {"wineprefixes": []}), None)
    iterate_until(lambda: view.btn_find_prefixes.get_sensitive())
    assert view.list_prefixes.get_first_child() is None
    assert view.stack_prefixes.get_visible_child_name() == "empty"
    assert messages == []


def test_prefix_search_exception_reports_failure_and_unlocks_button(import_page, iterate_until):
    view, callbacks, messages = import_page
    view._ImporterView__search_prefixes(view.btn_find_prefixes)
    callbacks.pop()(None, RuntimeError("Permission denied"))
    iterate_until(lambda: view.btn_find_prefixes.get_sensitive())
    assert messages == ["Permission denied"]
    assert view.btn_select_prefixes.get_sensitive()
    assert view.stack_prefixes.get_visible_child_name() == "empty"


def test_import_exception_reports_failure(import_page, iterate_until):
    view, _callbacks, messages = import_page
    view._ImporterView__finish(None, RuntimeError("Bottle is not private"))
    iterate_until(lambda: bool(messages))
    assert messages == ["Bottle is not private"]


def test_prefix_row_import_exception_restores_controls(import_page, monkeypatch, tmp_path, iterate_until):
    from bottles.frontend.widgets import importer as rows

    view, _callbacks, messages = import_page
    (tmp_path / "bottle.yml").write_text("Name: Office\n")
    view.import_manager.import_bottle = object()
    row = rows.ImporterEntry(view, {
        "Name": "Office", "Manager": "Wine", "Path": str(tmp_path), "Lock": False,
    })
    callbacks = []
    monkeypatch.setattr(rows, "RunAsync", lambda _func, callback, **_kwargs: callbacks.append(callback))
    row.import_wineprefix(row.btn_import)
    assert not row.get_sensitive()
    callbacks.pop()(None, RuntimeError("Cannot read bottle"))
    iterate_until(lambda: row.get_sensitive())
    assert row.btn_import.get_visible()
    assert not row.img_lock.get_visible()
    assert messages == ["Cannot read bottle"]


def test_prefix_names_are_rendered_as_literal_text(import_page, widget_texts):
    view, _callbacks, _messages = import_page
    name = "Office & <Work>"
    row = importer.ImporterEntry(view, {
        "Name": name, "Manager": "Wine", "Path": "/opt/user/Office", "Lock": False,
    })
    assert not row.get_use_markup()
    assert name in widget_texts(row)
