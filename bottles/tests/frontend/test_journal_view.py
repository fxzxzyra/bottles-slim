"""Exercise the real ColumnView, model and search/severity signals."""

import pytest
from gi.repository import Gtk

from bottles.frontend.windows import journal as module


@pytest.fixture
def journal(monkeypatch):
    entries = {
        "1": {"severity": "error", "timestamp": "2026-01-02 12:00:00", "message": "Editor <failed> & stopped"},
        "2": {"severity": "info", "timestamp": "2026-01-02 11:00:00", "message": "Editor started"},
        "3": {"severity": "warning", "timestamp": "2026-01-01 10:00:00", "message": "Viewer is slow"},
    }
    monkeypatch.setattr(module.JournalManager, "get", lambda **_kwargs: entries)
    dialog = module.JournalDialog()
    yield dialog
    dialog.destroy()


def messages(dialog):
    return [dialog.store.get_item(i).values[2] for i in range(dialog.store.get_n_items())]


def test_journal_preserves_grouping_and_plain_message_text(journal):
    assert isinstance(journal.journal_view, Gtk.ColumnView)
    assert messages(journal) == ["", "Editor <failed> & stopped", "Editor started", "", "Viewer is slow"]
    assert journal.store.get_item(0).values[1] == "<b>2026-01-02</b>"
    assert journal.journal_view.get_columns().get_n_items() == 3


def test_journal_search_and_severity_combine_through_signals(journal, iterate_until):
    journal.search_entry.set_text("EDITOR")
    iterate_until(lambda: messages(journal) == ["", "Editor <failed> & stopped", "Editor started"])
    journal.btn_error.emit("clicked")
    assert messages(journal) == ["", "Editor <failed> & stopped"]
    assert journal.label_filter.get_text() == "Errors"
    journal.search_entry.set_text("no match")
    iterate_until(lambda: journal.store.get_n_items() == 0)
    journal.btn_all.emit("clicked")
    assert messages(journal) == []  # Resetting severity does not discard search.


def test_journal_columns_render_markup_only_for_trusted_fields(journal, iterate_until, widget_texts):
    journal.present()
    iterate_until(lambda: "Editor <failed> & stopped" in widget_texts(journal))
    labels = widget_texts(journal)
    assert "Error" in labels
    assert "2026-01-02" in labels
    assert "2026-01-02 12:00:00" in labels
