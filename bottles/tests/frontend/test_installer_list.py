"""Exercise built templates, actual rows and signal filtering, not list mocks."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from gi.repository import Adw, Gtk

from bottles.backend.managers.installer import InstallerManager
from bottles.backend.models.config import BottleConfig
from bottles.backend.utils.threading import RunAsync
from bottles.frontend.views import bottle_installers as module
from bottles.frontend.views.bottle_installers import InstallersView


def metadata(name, arch="win64", channel="stable"):
    return {"Name": name, "Description": "An application", "Grade": "Gold",
            "Arch": arch, "Channel": channel}


def list_rows(view):
    rows = []
    row = view.list_installers.get_first_child()
    while row is not None:
        rows.append(row)
        row = row.get_next_sibling()
    return rows


@pytest.fixture
def installer_page(monkeypatch):
    jobs = []
    window = Gtk.Window()
    window.settings = SimpleNamespace(get_boolean=lambda _key: False)
    window.manager = SimpleNamespace(
        supported_installers={},
        installer_manager=SimpleNamespace(
            refresh_catalog=Mock(return_value={}),
            supports_channel=InstallerManager.supports_channel,
        ),
    )
    view = InstallersView(SimpleNamespace(window=window), BottleConfig(Name="Initial"))
    window.set_child(view)
    monkeypatch.setattr(module, "RunAsync", lambda task, callback: jobs.append((task, callback)))
    yield view, jobs, window
    window.destroy()


def test_latest_request_wins_with_real_rows_and_removes_old_widgets(installer_page):
    view, jobs, _window = installer_page
    catalog = {"x32": metadata("Old editor", "win32"), "x64": metadata("New editor")}
    view.manager.installer_manager.refresh_catalog.return_value = catalog
    first = BottleConfig(Name="First", Arch="win32")
    second = BottleConfig(Name="Second", Arch="win64")

    # Populate first: subsequent refreshes must detach these actual GTK rows.
    view.update(config=first)
    jobs[0][1](jobs[0][0]())
    old_row, = list_rows(view)
    assert old_row.config is first
    view.update(config=first)
    view.update(config=second)
    stale_result = jobs[1][0]()
    fresh_result = jobs[2][0]()
    jobs[2][1](fresh_result)
    jobs[1][1](stale_result)

    row, = list_rows(view)
    assert old_row.get_parent() is None
    assert row.config is second
    assert row.installer[0] == "x64"
    assert row.get_title() == "New editor"
    assert view.list_installers.get_sensitive()
    assert view.pref_page.get_visible()
    assert not view.status_page.get_visible()


def test_worker_exception_restores_empty_state_through_real_glib(
    installer_page, monkeypatch, iterate_until,
):
    view, _jobs, _window = installer_page
    # Keep RunAsync and its exception-to-callback path intact in this test.
    monkeypatch.setattr(module, "RunAsync", RunAsync)
    view.manager.installer_manager.refresh_catalog.side_effect = RuntimeError("offline")
    view.update()
    iterate_until(view.list_installers.get_sensitive)
    assert list_rows(view) == []
    assert view.status_page.get_visible()
    assert not view.pref_page.get_visible()
    assert not view.list_installers.get_visible()


@pytest.mark.parametrize("include_unstable, expected", [
    (False, ["editor"]), (True, ["editor", "preview"]),
])
def test_search_and_channel_filter_use_real_widgets(
    installer_page, iterate_until, include_unstable, expected,
):
    view, jobs, window = installer_page
    window.settings.get_boolean = lambda _key: include_unstable
    view.manager.installer_manager.refresh_catalog.return_value = {
        "editor": metadata("Straße Editor"), "preview": metadata("Preview", channel="rc"),
        "other-arch": metadata("Legacy", "win32"),
    }
    view.update()
    jobs[0][1](jobs[0][0]())
    rows = list_rows(view)
    assert [row.installer[0] for row in rows] == expected
    # 'changed' must be wired to the real filter. A constant-True filter fails.
    view.entry_search.set_text("STRASSE")
    iterate_until(lambda: all(row.get_child_visible() == (row.installer[0] == "editor") for row in rows))
    assert [row.get_title() for row in rows if row.get_child_visible()] == ["Straße Editor"]
    view.entry_search.set_text("no-such-application")
    iterate_until(lambda: all(not row.get_child_visible() for row in rows))
    view.entry_search.set_text("")
    iterate_until(lambda: all(row.get_child_visible() for row in rows))


def test_views_own_controllers_and_rows_independently(installer_page):
    view, jobs, window = installer_page
    view.manager.installer_manager.refresh_catalog.return_value = {"editor": metadata("Editor")}
    other = InstallersView(SimpleNamespace(window=window), BottleConfig(Name="Other"))
    assert view.ev_controller is not other.ev_controller
    assert view.ev_controller.get_widget() is view.entry_search
    assert other.ev_controller.get_widget() is other.entry_search
    view.update()
    jobs[0][1](jobs[0][0]())
    other.update()
    jobs[1][1](jobs[1][0]())
    view.empty_list()
    assert list_rows(view) == []
    assert len(list_rows(other)) == 1


def test_search_handles_missing_subtitle_and_rejects_nonmatches():
    row = Adw.ActionRow(title="Editor")
    assert InstallersView._InstallersView__filter_installers(row, None)
    assert InstallersView._InstallersView__filter_installers(row, "EDITOR")
    assert not InstallersView._InstallersView__filter_installers(row, "browser")
