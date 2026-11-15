"""Boundary formatting and real SQLite/cache integration for displayed playtime."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

from bottles.backend.managers.playtime import ProcessSessionTracker
from bottles.frontend.utils import playtime as module
from bottles.frontend.utils.playtime import PlaytimeRecord, PlaytimeService


@pytest.fixture(autouse=True)
def untranslated_messages(monkeypatch):
    # Translation is an external boundary; date/duration/escaping remain real.
    monkeypatch.setattr(module, "_", lambda message: message)


@pytest.mark.parametrize("seconds, expected", [
    (0, "<1m"), (30, "<1m"), (59, "<1m"), (60, "1m"),
    (150, "2m"), (3599, "59m"), (3600, "1h 00m"),
    (3660, "1h 01m"), (7325, "2h 02m"),
    (86400, "1d 00h"), (90000, "1d 01h"), (180000, "2d 02h"),
])
def test_format_playtime(seconds, expected):
    assert PlaytimeService.format_playtime(seconds) == expected


@pytest.mark.parametrize("played, expected", [
    (None, "Never"),
    (datetime(2025, 2, 10, 0, 0), "Today"),
    (datetime(2025, 2, 9, 23, 59), "Yesterday"),
    (datetime(2025, 2, 8, 0, 0), "2 days ago"),
    (datetime(2025, 2, 4, 0, 0), "6 days ago"),
    (datetime(2025, 2, 3, 0, 0), datetime(2025, 2, 3).strftime("%x")),
])
def test_format_last_played_at_calendar_boundaries(played, expected):
    with freeze_time("2025-02-10 00:01:00"):
        assert PlaytimeService.format_last_played(played) == expected


@pytest.mark.parametrize("seconds, count, expected", [
    (7325, 3, "Last Played: Today – Playtime: 2h 02m"),
    (30, 1, "Last Played: Today – Playtime: &lt;1m"),
    (0, 0, "Never Played"),
])
def test_subtitle_includes_date_and_duration_and_escapes_markup(seconds, count, expected):
    service = PlaytimeService(SimpleNamespace(settings=SimpleNamespace(get_boolean=lambda _: False)))
    record = PlaytimeRecord(
        bottle_id="b1", program_id="p1", program_name="Editor", program_path="/path",
        total_seconds=seconds, sessions_count=count, last_played=datetime(2025, 2, 10),
    )
    with freeze_time("2025-02-10 00:01:00"):
        assert service.format_subtitle(record) == expected
    assert service.format_subtitle(None) == "Never Played"


def test_translated_date_is_escaped_before_subtitle_interpolation(monkeypatch):
    monkeypatch.setattr(module, "_", lambda text: "<Today & now>" if text == "Today" else text)
    service = PlaytimeService(SimpleNamespace(settings=SimpleNamespace(get_boolean=lambda _: False)))
    record = PlaytimeRecord(
        bottle_id="b1", program_id="p1", program_name="Editor", program_path="/path",
        total_seconds=30, sessions_count=1, last_played=datetime(2025, 2, 10),
    )
    with freeze_time("2025-02-10 00:01:00"):
        assert service.format_subtitle(record) == (
            "Last Played: &lt;Today &amp; now&gt; – Playtime: &lt;1m"
        )


def test_service_reads_persisted_totals_and_refreshes_only_invalidated_program(tmp_path):
    tracker = ProcessSessionTracker(db_path=str(tmp_path / "metrics.sqlite"), heartbeat_interval=3600)
    service = PlaytimeService(SimpleNamespace(settings=SimpleNamespace(get_boolean=lambda _: tracker.enabled), get_playtime_tracker=lambda _: tracker))

    def finish(program, seconds):
        sid = tracker.start_session(
            bottle_id="b1", bottle_name="Office", bottle_path="/bottle",
            program_name=program, program_path=f"C:/Office/{program}.exe",
        )
        clock.tick(seconds)
        tracker.mark_exit(sid, status="success")

    def record(program):
        return service.get_program_playtime("b1", "/bottle", program, f"C:/Office/{program}.exe")

    try:
        with freeze_time("2025-01-01 12:00:00") as clock:
            finish("editor", 10)
            finish("viewer", 5)
            editor = record("editor")
            viewer = record("viewer")
            assert (editor.total_seconds, editor.sessions_count) == (10, 1)
            assert (viewer.total_seconds, viewer.sessions_count) == (5, 1)
            finish("editor", 7)
            assert record("editor").total_seconds == 10  # Live cache before invalidation.
            service.invalidate_program("b1", "/bottle", "C:/Office/editor.exe")
            refreshed = record("editor")
            assert (refreshed.total_seconds, refreshed.sessions_count) == (17, 2)
            assert record("viewer") is viewer  # Unrelated cached record is preserved.
            total = service.get_bottle_playtime("b1")
            assert (total.total_seconds, total.sessions_count) == (22, 3)
            tracker.disable_tracking()
            assert service.get_program_playtime("b1", "/bottle", "editor", "C:/Office/editor.exe") is None
    finally:
        tracker.shutdown()
