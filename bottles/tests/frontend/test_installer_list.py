from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bottles.backend.models.config import BottleConfig
from bottles.frontend.views import bottle_installers as module
from bottles.frontend.views.bottle_installers import InstallersView


@pytest.fixture
def installer_list(monkeypatch):
    jobs = []
    rows = []
    view = SimpleNamespace(
        config=BottleConfig(Name="Initial"),
        window=SimpleNamespace(settings=SimpleNamespace(get_boolean=lambda _key: False)),
        manager=SimpleNamespace(
            supported_installers={},
            installer_manager=SimpleNamespace(
                refresh_catalog=lambda: {}, supports_channel=lambda *_args: True,
            ),
        ),
        list_installers=Mock(), status_page=Mock(), pref_page=Mock(),
        _InstallersView__update_generation=0,
        _InstallersView__registry=rows,
    )
    view.empty_list = lambda: rows.clear()
    monkeypatch.setattr(module, "RunAsync", lambda task, callback: jobs.append((task, callback)))
    monkeypatch.setattr(module, "InstallerEntry", lambda **kwargs: kwargs)
    return view, jobs, rows


def test_newer_installer_request_wins_and_keeps_matching_bottle(installer_list):
    view, jobs, rows = installer_list
    first = BottleConfig(Name="First", Arch="win32")
    second = BottleConfig(Name="Second", Arch="win64")
    catalog = {"x32": {"Arch": "win32"}, "x64": {"Arch": "win64"}}
    view.manager.installer_manager.refresh_catalog = lambda: catalog
    InstallersView.update(view, config=first)
    InstallersView.update(view, config=second)
    first_result = jobs[0][0]()
    second_result = jobs[1][0]()
    assert first_result.data["entries"] == [("x32", catalog["x32"])]
    assert second_result.data["entries"] == [("x64", catalog["x64"])]

    jobs[1][1](second_result)
    jobs[0][1](first_result)

    assert len(rows) == 1
    assert rows[0]["config"] is second
    assert rows[0]["installer"][0] == "x64"
    view.list_installers.append.assert_called_once()


def test_installer_refresh_exception_restores_controls(installer_list):
    view, jobs, rows = installer_list
    InstallersView.update(view)
    jobs[0][1](None, RuntimeError("offline"))
    view.list_installers.set_sensitive.assert_called_with(True)
    view.status_page.set_visible.assert_called_with(True)
    assert not rows


def test_search_accepts_missing_subtitle_and_empty_terms():
    row = SimpleNamespace(get_title=lambda: "Editor", get_subtitle=lambda: None)
    assert InstallersView._InstallersView__filter_installers(row, None)
    assert InstallersView._InstallersView__filter_installers(row, "EDITOR")
