# ruff: noqa: E402

from types import SimpleNamespace

import pytest


from bottles.frontend.views import new_bottle_dialog
from bottles.frontend.views.new_bottle_dialog import BottlesNewBottleDialog

INVALID_LIST_POSITION = 4294967295


def _make_dialog(runners, dxvks, selected=0):
    return SimpleNamespace(
        set_can_close=lambda _value: None,
        stack_create=SimpleNamespace(set_visible_child_name=lambda _name: None),
        _cancel_requested=None,
        _BottlesNewBottleDialog__reset_creation_steps=lambda: None,
        _BottlesNewBottleDialog__clear_creation_task=lambda: None,
        btn_cancel_creating=SimpleNamespace(
            set_sensitive=lambda _value: None,
            set_label=lambda _label: None,
        ),
        _runner_ids=list(runners),
        combo_runner=SimpleNamespace(get_selected=lambda: selected),
        combo_arch=SimpleNamespace(get_selected=lambda: 0),
        switch_sandbox=SimpleNamespace(get_active=lambda: False),
        entry_name=SimpleNamespace(get_text=lambda: "Bottle"),
        manager=SimpleNamespace(
            runners_available=runners,
            dxvk_available=dxvks,
            create_bottle=lambda **_kwargs: None,
        ),
        arch={"win64": "64-bit"},
        custom_path="/selected/empty",
        _BottlesNewBottleDialog__check_validity=lambda: (False, False),
        selected_environment="gaming",
        env_recipe_path=None,
        runner=None,
        update_output=lambda _text: None,
        finish=lambda *_args, **_kwargs: None,
        _creation_task=None,
        _creation_cancel_event=None,
        _creation_job=None,
    )


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        new_bottle_dialog,
        "RunAsync",
        lambda **kwargs: calls.update(kwargs) or SimpleNamespace(),
    )
    monkeypatch.setattr(
        new_bottle_dialog,
        "Task",
        lambda **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        new_bottle_dialog.TaskManager,
        "add",
        staticmethod(lambda _task: None),
    )
    return calls


@pytest.mark.parametrize(
    ("runners", "dxvks", "selected", "expected_runner", "expected_dxvk"),
    (
        (["soda-11.0-4"], ["dxvk-2.7"], 0, "soda-11.0-4", "dxvk-2.7"),
        (["soda-11.0-4"], [], 0, "soda-11.0-4", False),
    ),
)
def test_create_bottle_uses_selected_runner_with_optional_dxvk(
    captured, runners, dxvks, selected, expected_runner, expected_dxvk
):
    dialog = _make_dialog(runners, dxvks, selected)

    BottlesNewBottleDialog.create_bottle(dialog)

    assert captured["runner"] == expected_runner
    assert captured["dxvk"] == expected_dxvk


def test_create_bottle_requires_directory(captured):
    dialog = _make_dialog(["system-wine"], [])
    dialog.custom_path = ""
    BottlesNewBottleDialog.create_bottle(dialog)
    assert captured == {}


def test_missing_directory_disables_create_without_marking_a_valid_name_as_invalid():
    state = {}
    view = SimpleNamespace(
        custom_path="",
        _runner_ids=["system-wine"],
        combo_runner=SimpleNamespace(get_selected=lambda: 0),
        _BottlesNewBottleDialog__check_validity=lambda: (False, False),
        btn_create=SimpleNamespace(set_sensitive=lambda value: state.update(enabled=value)),
        menu_duplicate=SimpleNamespace(set_visible=lambda value: state.update(duplicate=value)),
        entry_name=SimpleNamespace(
            add_css_class=lambda _: state.update(error=True),
            remove_css_class=lambda _: state.update(error=False),
        ),
    )
    BottlesNewBottleDialog._BottlesNewBottleDialog__check_entry_name(view)
    assert state == {"enabled": False, "duplicate": False, "error": False}


@pytest.mark.parametrize("runners, selected", [([], INVALID_LIST_POSITION), (["system-wine"], INVALID_LIST_POSITION)])
def test_create_without_a_selected_runner_never_enters_progress(captured, runners, selected):
    dialog = _make_dialog(runners, [], selected)
    def unexpected(*_args):
        raise AssertionError("Missing runner must not enter the creation page")
    dialog.stack_create.set_visible_child_name = unexpected
    dialog.set_can_close = unexpected
    BottlesNewBottleDialog.create_bottle(dialog)
    assert captured == {}
    assert dialog._creation_task is None


def test_create_is_disabled_without_a_runner_but_the_name_remains_valid():
    state = {}
    view = SimpleNamespace(
        custom_path="/selected/empty", _runner_ids=[],
        combo_runner=SimpleNamespace(get_selected=lambda: INVALID_LIST_POSITION),
        _BottlesNewBottleDialog__check_validity=lambda: (False, False),
        btn_create=SimpleNamespace(set_sensitive=lambda value: state.update(enabled=value)),
        menu_duplicate=SimpleNamespace(set_visible=lambda value: state.update(duplicate=value)),
        entry_name=SimpleNamespace(
            add_css_class=lambda _: state.update(error=True),
            remove_css_class=lambda _: state.update(error=False),
        ),
    )
    BottlesNewBottleDialog._BottlesNewBottleDialog__check_entry_name(view)
    assert state == {"enabled": False, "duplicate": False, "error": False}


def test_runner_refresh_preserves_selection_and_includes_new_registration():
    from gi.repository import Adw, Gtk

    model = Gtk.StringList.new(["First", "Second"])
    combo = Adw.ComboRow(model=model, selected=1)
    checks = []
    dialog = SimpleNamespace(
        combo_runner=combo, str_list_runner=model, _runner_ids=["system-wine", "custom-wine"],
        manager=SimpleNamespace(runners_available=["new-system-wine", "system-wine", "custom-wine", "new-custom-wine"]),
        _BottlesNewBottleDialog__check_entry_name=lambda: checks.append(True),
    )
    BottlesNewBottleDialog._BottlesNewBottleDialog__refresh_runners(dialog)
    assert dialog._runner_ids[combo.get_selected()] == "custom-wine"
    assert model.get_n_items() == 4
    assert checks == [True]
