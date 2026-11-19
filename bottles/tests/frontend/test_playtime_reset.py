from types import SimpleNamespace
from unittest.mock import Mock

from gi.repository import Adw, Gtk

from bottles.backend.managers.playtime import ProcessSessionTracker, _compute_program_id
from bottles.frontend.utils.playtime import PlaytimeService


from bottles.frontend.windows.playtimegraph import PlaytimeGraphDialog


def test_reset_invalidates_the_shared_program_cache(tmp_path):
    tracker = ProcessSessionTracker(db_path=str(tmp_path / "playtime.sqlite"))
    try:
        path = str(tmp_path / "drive_c/game.exe")
        session = tracker.start_session(
            bottle_id="test", bottle_name="test", bottle_path=str(tmp_path),
            program_name="Game", program_path=path,
        )
        tracker.mark_exit(session)
        manager = SimpleNamespace(
            get_playtime_tracker=lambda bottle_id: tracker,
            settings=SimpleNamespace(get_boolean=lambda _key: True),
        )
        service = manager.playtime_service = PlaytimeService(manager)
        record = service.get_program_playtime("test", str(tmp_path), "Game", path)
        assert record is not None
        program_id = _compute_program_id("test", str(tmp_path), path)
        parent = SimpleNamespace(manager=manager, update_playtime=Mock())
        dialog = SimpleNamespace(
            bottle_id="test", program_id=program_id, program_name="Game", parent=parent,
            current_week_offset=-1, _PlaytimeGraphDialog__load_data=Mock(),
        )

        PlaytimeGraphDialog._PlaytimeGraphDialog__on_reset_confirmed(dialog, None, "reset")

        assert service.cache.get("test", program_id) is None
        assert service.get_program_playtime("test", str(tmp_path), "Game", path) is None
        parent.update_playtime.assert_called_once_with(service)
        assert dialog.current_week_offset == 0
    finally:
        tracker.shutdown()


def test_reset_dialog_cancel_preserves_stats_and_confirm_clears_them(tmp_path):
    tracker = ProcessSessionTracker(db_path=str(tmp_path / "playtime.sqlite"))
    Adw.init()
    window = Gtk.Window()
    dialog = None
    try:
        path = str(tmp_path / "drive_c/game.exe")
        session = tracker.start_session(
            bottle_id="test", bottle_name="test", bottle_path=str(tmp_path),
            program_name="Game", program_path=path,
        )
        tracker.mark_exit(session)
        program_id = _compute_program_id("test", str(tmp_path), path)
        manager = SimpleNamespace(
            get_playtime_tracker=lambda bottle_id: tracker,
            settings=SimpleNamespace(get_boolean=lambda _key: True),
        )
        window.manager = manager
        parent = SimpleNamespace(window=window, manager=manager, update_playtime=Mock())
        dialog = PlaytimeGraphDialog(parent, "Game", program_id, "test")

        dialog.btn_reset.emit("clicked")
        confirmation = next(w for w in Gtk.Window.get_toplevels() if isinstance(w, Adw.MessageDialog))
        confirmation.response("cancel")
        assert tracker.get_totals("test", program_id) is not None
        parent.update_playtime.assert_not_called()

        dialog.btn_reset.emit("clicked")
        confirmation = next(w for w in Gtk.Window.get_toplevels() if isinstance(w, Adw.MessageDialog))
        confirmation.response("reset")
        assert tracker.get_totals("test", program_id) is None
        parent.update_playtime.assert_called_once()
    finally:
        if dialog is not None:
            dialog.destroy()
        window.destroy()
        tracker.shutdown()


def test_usage_statistics_fit_a_narrow_window_and_keep_the_full_program_name(tmp_path):
    Adw.init()
    tracker = ProcessSessionTracker(db_path=str(tmp_path / "playtime.sqlite"))
    window = Gtk.Window()
    dialog = None
    try:
        manager = SimpleNamespace(
            get_playtime_tracker=lambda _bottle_id: tracker,
            settings=SimpleNamespace(get_boolean=lambda _key: True),
        )
        parent = SimpleNamespace(window=window, manager=manager)
        name = "A very long program name " * 30
        dialog = PlaytimeGraphDialog(parent, name, "program", "container")
        assert dialog.get_title() == name
        assert dialog.label_program_title.get_tooltip_text() == name
        # Measure real template contents, including charts and long titles.
        # The former fixed 600px content and unbounded label both violate this.
        minimum, *_ = dialog.get_child().measure(Gtk.Orientation.HORIZONTAL, -1)
        assert minimum <= 480
    finally:
        if dialog is not None:
            dialog.destroy()
        window.destroy()
        tracker.shutdown()
