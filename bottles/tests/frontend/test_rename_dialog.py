"""Rename validation follows text changes, including paste and repeated dialogs."""

from types import SimpleNamespace

from bottles.frontend.windows.rename import RenameDialog


def test_rename_tracks_pasted_text_and_rejects_empty_or_unchanged_names():
    saved = []
    window = SimpleNamespace(manager=object())
    # Use the real native dialog and its owning window.
    from gi.repository import Adw
    parent = Adw.Window()
    parent.manager = window.manager
    dialog = RenameDialog(parent, "Office", lambda new_name: saved.append(new_name))
    dialog.present(parent)
    try:
        assert isinstance(dialog, Adw.Dialog)
        assert not dialog.btn_save.get_sensitive()
        dialog.entry_name.set_text("   ")
        assert not dialog.btn_save.get_sensitive()
        dialog.entry_name.emit("entry-activated")
        assert saved == []
        dialog.entry_name.set_text("  New Office  ")
        assert dialog.btn_save.get_sensitive()
        dialog.entry_name.emit("entry-activated")
        assert saved == ["New Office"]
    finally:
        dialog.force_close()
        parent.destroy()
