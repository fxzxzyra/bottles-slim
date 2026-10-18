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


def test_empty_library_add_card_opens_existing_bottle_programs():
    from bottles.frontend.widgets.library import LibraryAddEntry

    calls = []
    window = SimpleNamespace(
        show_list_view=lambda: calls.append("bottles"),
        show_toast=lambda message: calls.append(message),
    )
    view = SimpleNamespace(window=window)
    view.show_bottle_programs = lambda *args: LibraryView.show_bottle_programs(view, *args)
    card = LibraryAddEntry(view)

    card.btn_bottle.emit("clicked")

    assert calls == [
        "bottles",
        "Open a Bottle and choose Add to Library from one of its programs.",
    ]
