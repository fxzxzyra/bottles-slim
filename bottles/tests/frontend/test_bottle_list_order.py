from types import SimpleNamespace

import pytest


from bottles.frontend.views.list import (  # noqa: E402
    BottlesBottleRow,
    BottleView,
    _bottle_order_id,
    _ordered_bottles,
    _replace_group_order,
)


def _config(path, environment="Gaming"):
    from bottles.backend.models.config import BottleConfig
    return BottleConfig(Name=path, Path=path, Environment=environment)


def test_default_bottle_order_uses_display_names_without_case():
    alpha = _config("old-z-folder")
    alpha.Name = "alpha"
    beta = _config("old-a-folder")
    beta.Name = "Beta"
    assert _ordered_bottles([beta, alpha], []) == [alpha, beta]
    alpha.Name = "Zulu"
    assert _ordered_bottles([alpha, beta], []) == [beta, alpha]


def test_ordered_bottles_keeps_new_bottles_at_the_end():
    alpha = _config("Alpha")
    beta = _config("Beta")
    gamma = _config("Gamma")

    ordered = _ordered_bottles(
        [alpha, beta, gamma],
        [_bottle_order_id(beta), _bottle_order_id(alpha)],
    )

    assert [config.Path for config in ordered] == ["Beta", "Alpha", "Gamma"]


def test_replace_group_order_keeps_unavailable_entries():
    configured = [
        "bottle:Alpha",
        "bottle:Unavailable",
        "bottle:Beta",
    ]

    result = _replace_group_order(
        configured,
        ["bottle:Alpha", "bottle:Beta", "bottle:Gamma"],
        ["bottle:Gamma", "bottle:Beta", "bottle:Alpha"],
    )

    assert result == [
        "bottle:Gamma",
        "bottle:Unavailable",
        "bottle:Beta",
        "bottle:Alpha",
    ]


def test_bottle_row_refreshes_programs_after_executable_finishes():
    calls = []
    config = _config("Test")
    row = SimpleNamespace(
        config=config,
        manager=SimpleNamespace(
            get_programs=lambda called_config, **kwargs: calls.append(
                (called_config, kwargs)
            )
        ),
    )

    BottlesBottleRow._on_executable_finished(row)

    assert calls == [(config, {"force_update": True})]


def test_reorder_bottle_orders_applications_and_games_together():
    alpha = _config("Alpha")
    beta = _config("Beta")
    application = _config("Office", "Application")
    configured = [
        _bottle_order_id(alpha),
        _bottle_order_id(application),
        _bottle_order_id(beta),
    ]
    saved = []
    refreshes = []
    settings = SimpleNamespace(
        get_strv=lambda _key: configured,
        set_strv=lambda _key, value: saved.extend(value),
    )
    view = SimpleNamespace(
        window=SimpleNamespace(
            settings=settings,
            manager=SimpleNamespace(
                local_bottles={
                    "Alpha": alpha,
                    "Beta": beta,
                    "Office": application,
                }
            ),
        ),
        update_bottles_list=lambda **kwargs: refreshes.append(kwargs),
    )

    BottleView._BottleView__reorder_bottle(view, SimpleNamespace(config=beta), "top")

    assert saved == [
        _bottle_order_id(beta),
        _bottle_order_id(alpha),
        _bottle_order_id(application),
    ]
    assert refreshes == [{"refresh_updates": False}]


@pytest.mark.parametrize(
    ("titles", "terms", "expected"),
    [([], "", "empty"), (["Alpha"], "alpha", "list"),
     (["Alpha"], "missing", "no-results")],
)
def test_bottle_list_empty_state(titles, terms, expected, monkeypatch):
    from bottles.backend.state import SignalManager
    monkeypatch.setattr(SignalManager, "_SIGNALS", {})
    monkeypatch.setattr(BottleView, "update_bottles_list", lambda self: None)
    view = BottleView(SimpleNamespace(show_add_view=lambda *_: None))
    view._BottleView__bottles = {}
    from gi.repository import Adw, Gtk
    for title in titles:
        row = Adw.ActionRow(title=title)
        view.list_bottles.append(row)
        view._BottleView__bottles[title] = row
    view.entry_search.set_text(terms)
    view._BottleView__update_empty_state(terms)
    assert view.content_stack.get_visible_child_name() == expected
    shown = view.content_stack.get_visible_child()
    assert shown is {"list": view.pref_page, "empty": view.bottle_status,
                     "no-results": view.no_bottles_found}[expected]
    # Each state owns its scrolling; no outer scroller wraps a scrolling page.
    assert isinstance(view.get_child(), Gtk.Box)
    assert shown.get_parent() is view.content_stack


def test_search_updates_filters_and_empty_state():
    filters = []
    empty_states = []
    filter_bottles = BottleView._BottleView__filter_bottles
    bottle_list = SimpleNamespace(
        set_filter_func=lambda callback, terms: filters.append((callback, terms))
    )
    view = SimpleNamespace(
        _BottleView__filter_bottles=filter_bottles,
        _BottleView__update_empty_state=empty_states.append,
        list_bottles=bottle_list,
    )

    BottleView._BottleView__search_bottles(
        view, SimpleNamespace(get_text=lambda: "missing")
    )

    assert filters == [
        (filter_bottles, "missing"),
    ]
    assert empty_states == ["missing"]


def test_bottle_order_is_stable_after_rename_and_move_and_distinct_for_copies():
    from bottles.backend.models.config import BottleConfig
    original = BottleConfig(Name="Office", Path="/original")
    other = BottleConfig(Name="Other", Path="/other")
    order = [_bottle_order_id(original), _bottle_order_id(other)]
    original.Name, original.Path = "Renamed", "/moved"
    clone = BottleConfig(Name=original.Name, Path=original.Path)
    assert _bottle_order_id(original) == order[0] == original.Id
    assert _bottle_order_id(clone) != order[0]
    assert _ordered_bottles([clone, other, original], order) == [original, other, clone]


@pytest.mark.parametrize("environment", ["Application", "Gaming", "Custom"])
def test_bottle_row_displays_the_translated_environment(environment, monkeypatch, widget_texts):
    from bottles.frontend.utils import common
    monkeypatch.setattr(common, "_", lambda text: "Translated " + text)
    window = SimpleNamespace(manager=object(), settings=SimpleNamespace(get_boolean=lambda _: False))
    row = BottlesBottleRow(window, _config("/opt/Wine", environment=environment))
    assert "Translated " + environment in widget_texts(row.wrap_box)
    assert row.config.Environment == environment
