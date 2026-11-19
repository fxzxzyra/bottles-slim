from types import SimpleNamespace
from unittest.mock import Mock

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.frontend.widgets import program as program_module
from bottles.frontend.widgets.program import ProgramEntry
from bottles.frontend.windows.window import BottlesWindow


def test_toast_action_works_without_dismiss_callback():
    toasts = []
    action = Mock()
    window = SimpleNamespace(toasts=SimpleNamespace(add_toast=toasts.append))
    BottlesWindow.show_toast(window, "Ready", action_label="Open", action_callback=action)
    toasts[0].emit("button-clicked")
    action.assert_called_once_with(toasts[0])


def test_toast_blocks_dismiss_before_running_undo_action():
    toasts = []
    dismissed = Mock()
    window = SimpleNamespace(toasts=SimpleNamespace(add_toast=toasts.append))
    BottlesWindow.show_toast(
        window, "Removed", action_label="Undo",
        action_callback=lambda toast: toast.emit("dismissed"),
        dismissed_callback=dismissed,
    )
    toasts[0].emit("button-clicked")
    dismissed.assert_not_called()


def test_program_rename_preserves_user_cover_and_does_not_fetch_remote(monkeypatch):
    saved = []
    config = BottleConfig(Name="Test")
    key = (config.Id, "library-id")
    entries = {key: {"id": "program-id", "name": "Old", "thumbnail": "grid:personal.png"}}
    library = SimpleNamespace(
        get_library=lambda: entries,
        save_library=lambda: saved.append(dict(entries[key])),
        download_thumbnail=Mock(side_effect=AssertionError("rename must preserve the cover")),
    )
    view = SimpleNamespace(
        program={"id": "program-id", "name": "Old"},
        config=config,
        manager=SimpleNamespace(update_config=lambda **_kwargs: Result(True, {"config": config})),
        window=Mock(), update_programs=Mock(),
    )
    callbacks = []
    monkeypatch.setattr(program_module.ManagerUtils, "has_desktop_entry", lambda *_args: False)
    monkeypatch.setattr(program_module, "LibraryManager", lambda: library)
    monkeypatch.setattr(program_module, "RunAsync", lambda task, callback: task())
    monkeypatch.setattr(program_module, "RenameDialog", lambda _window, **kwargs: (
        callbacks.append(kwargs["on_save"]) or SimpleNamespace(present=lambda parent: None)
    ))

    ProgramEntry.rename_program(view, None)
    callbacks[0]("New")

    assert view.program["name"] == "New"
    assert saved == [{"id": "program-id", "name": "New", "thumbnail": "grid:personal.png"}]
    library.download_thumbnail.assert_not_called()


def test_corrupt_cover_keeps_card_placeholder(monkeypatch):
    from bottles.frontend.widgets import library as library_module
    from bottles.frontend.widgets.library import LibraryEntry

    cover = Mock()
    placeholder = Mock()
    monkeypatch.setattr(
        library_module, "Gdk",
        SimpleNamespace(Texture=SimpleNamespace(
            new_from_filename=Mock(side_effect=library_module.GLib.Error("bad image"))
        )),
    )
    entry = SimpleNamespace(img_cover=cover, label_no_cover=placeholder)
    LibraryEntry._LibraryEntry__set_cover(entry, "corrupt.png")
    cover.set_paintable.assert_not_called()
    placeholder.set_visible.assert_not_called()


def test_slow_cover_download_cannot_overwrite_new_selection(monkeypatch):
    from bottles.frontend.widgets import library as library_module
    from bottles.frontend.widgets.library import LibraryEntry

    manager = SimpleNamespace(
        get_library=lambda: {("bottle-id", "entry"): {"thumbnail": "grid:new-selection.png"}},
        save_library=Mock(),
    )
    monkeypatch.setattr(library_module, "LibraryManager", lambda: manager)
    entry = SimpleNamespace(library_key=("bottle-id", "entry"), _LibraryEntry__set_cover=Mock())
    LibraryEntry._LibraryEntry__apply_downloaded_cover(
        entry, "grid:downloaded.png", "grid:old-missing.png"
    )
    manager.save_library.assert_not_called()
    entry._LibraryEntry__set_cover.assert_not_called()
