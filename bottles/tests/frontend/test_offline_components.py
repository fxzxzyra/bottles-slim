# ruff: noqa: E402
from types import MethodType, SimpleNamespace

import pytest
from gi.repository import Adw


from bottles.frontend.views.preferences import PreferencesDialog


def _view(installed):
    Adw.init()
    manager = SimpleNamespace(
        get_offline_components=lambda *_args: installed,
        component_manager=SimpleNamespace(is_in_use=lambda *_args: False),
        external_runners=set(),
        utils_conn=SimpleNamespace(status=False),
    )
    view = SimpleNamespace(window=SimpleNamespace(
        manager=manager, settings=SimpleNamespace(get_boolean=lambda _key: False)
    ), manager=manager, _PreferencesDialog__registry=[])
    view._PreferencesDialog__display_unstable_candidate = MethodType(
        PreferencesDialog._PreferencesDialog__display_unstable_candidate, view
    )
    return view


def test_installed_dll_is_manageable_without_a_catalog():
    view = _view(["dxvk-2.7"])

    count = PreferencesDialog._PreferencesDialog__populate_component_list(
        view, "dxvk", {}, Adw.ExpanderRow()
    )

    assert count == 1
    entry = view._PreferencesDialog__registry[0]
    assert entry.get_title() == "dxvk-2.7"
    assert entry.btn_remove.get_visible()



@pytest.mark.parametrize("installed", (True, False))
def test_installed_candidates_remain_visible_when_candidates_are_disabled(installed):
    view = _view([])

    shown = view._PreferencesDialog__display_unstable_candidate(
        ["dxvk-test", {"Channel": "unstable", "Installed": installed}]
    )

    assert shown is installed
