# ruff: noqa: E402

from types import SimpleNamespace

from bottles.frontend.views import library as library_module
from bottles.frontend.views.library import LibraryView, _ordered_library_entries


def test_library_entries_are_ordered_by_name():
    entries = {
        "third": {"name": "Zulu"},
        "first": {"name": "alpha"},
        "second": {"name": "Bravo"},
    }

    ordered = _ordered_library_entries(entries)

    assert [entry_uuid for entry_uuid, _entry in ordered] == [
        "first",
        "second",
        "third",
    ]


def test_delete_entry_refreshes_library(monkeypatch):
    removed = []
    updates = []
    manager = SimpleNamespace(
        remove_from_library=lambda entry_uuid, config: removed.append(
            (entry_uuid, config)
        )
    )
    monkeypatch.setattr(library_module, "LibraryManager", lambda: manager)
    view = SimpleNamespace(update=lambda: updates.append(True))
    entry = SimpleNamespace(uuid="entry-id", config="config")

    LibraryView._LibraryView__delete_entry(view, entry)

    assert removed == [("entry-id", "config")]
    assert updates == [True]


def test_empty_library_opens_existing_bottles(monkeypatch):
    calls = []
    monkeypatch.setattr(library_module, "LibraryManager", lambda: SimpleNamespace(get_library=lambda: {}))
    view = LibraryView(SimpleNamespace(show_list_view=lambda: calls.append("bottles")))
    assert view.library_stack.get_visible_child_name() == "empty"
    assert view.main_flow.get_first_child() is None
    view.btn_browse_bottles.emit("clicked")
    assert calls == ["bottles"]


def test_library_returns_to_empty_state_after_last_program_is_removed(monkeypatch):
    from gi.repository import Gtk

    entries = {"office": {"name": "Office"}}
    monkeypatch.setattr(library_module, "LibraryManager", lambda: SimpleNamespace(get_library=lambda: entries))
    # Card behavior has separate coverage; exercise the real view and Gtk container here.
    monkeypatch.setattr(library_module, "LibraryEntry", lambda *_args: Gtk.Label(label="Office"))
    view = LibraryView(SimpleNamespace())
    assert view.library_stack.get_visible_child_name() == "programs"
    assert view.main_flow.get_first_child() is not None
    entries.clear()
    view.update()
    assert view.library_stack.get_visible_child_name() == "empty"
    assert view.main_flow.get_first_child() is None


def test_card_keeps_its_full_name_and_actions_visible():
    from bottles.backend.models.config import BottleConfig
    from bottles.frontend.widgets.library import LibraryEntry

    name = "Office & <Work> with a long program name"
    config = BottleConfig(Name="Work")
    program = {"id": "office", "name": name}
    manager = SimpleNamespace(local_bottles={"Work": config}, get_programs=lambda _config: [program])
    library = SimpleNamespace(window=SimpleNamespace(manager=manager))
    card = LibraryEntry(library, "entry-id", {"id": "office", "name": name, "bottle": {"name": "Work"}})
    assert card.label_name.get_text() == name
    assert card.label_name.get_tooltip_text() == name
    assert card.revealer_details.get_reveal_child()
    assert card.btn_remove.get_visible()
    assert card.btn_cover.get_visible()


def test_library_does_not_disguise_unexpected_card_errors_as_an_empty_library(monkeypatch):
    import pytest

    entries = {"office": {"name": "Office"}}
    monkeypatch.setattr(library_module, "LibraryManager", lambda: SimpleNamespace(get_library=lambda: entries))
    def broken_card(*_args):
        raise RuntimeError("Broken card template")
    monkeypatch.setattr(library_module, "LibraryEntry", broken_card)
    with pytest.raises(RuntimeError, match="Broken card template"):
        LibraryView(SimpleNamespace())
