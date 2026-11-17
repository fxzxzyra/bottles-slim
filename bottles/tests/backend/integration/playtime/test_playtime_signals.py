"""Lifecycle signals must persist the correct session and ignore unrelated exits."""

import sqlite3
import time

import pytest
from freezegun import freeze_time

from bottles.backend.models.process import ProcessStartedPayload, ProcessFinishedPayload
from bottles.backend.models.result import Result
from bottles.backend.state import SignalManager, Signals

BOTTLE_ID = "1" * 32


@pytest.mark.parametrize("status", ["success", "unknown"])
def test_signals_persist_exact_duration_and_ignore_unrelated_exit(manager, status):
    started = ProcessStartedPayload(
        launch_id="launch-1", bottle_id=BOTTLE_ID, bottle_name="Bottle",
        bottle_path="/bottle", program_name="Editor", program_path="C:/App/editor.exe",
    )
    with freeze_time("2025-01-01 10:00:00") as clock:
        SignalManager.send(Signals.ProgramStarted, Result(True, started))
        with sqlite3.connect(manager.get_playtime_tracker(BOTTLE_ID).db_path) as connection:
            assert connection.execute("SELECT status FROM sessions").fetchall() == [("running",)]
            assert connection.execute("SELECT * FROM playtime_totals").fetchall() == []
        clock.tick(29)
        SignalManager.send(Signals.ProgramFinished, Result(True, ProcessFinishedPayload(
            bottle_id=BOTTLE_ID,
            launch_id="different-launch", status=status, ended_at=int(time.time()),
        )))
        with sqlite3.connect(manager.get_playtime_tracker(BOTTLE_ID).db_path) as connection:
            assert connection.execute("SELECT status FROM sessions").fetchall() == [("running",)]
        finished = Result(True, ProcessFinishedPayload(
            bottle_id=BOTTLE_ID,
            launch_id=started.launch_id, status=status, ended_at=int(time.time()),
        ))
        SignalManager.send(Signals.ProgramFinished, finished)
        # A repeated delivery must not double-count the duration or session.
        SignalManager.send(Signals.ProgramFinished, finished)

    with sqlite3.connect(manager.get_playtime_tracker(BOTTLE_ID).db_path) as connection:
        assert connection.execute(
            "SELECT status, duration_seconds FROM sessions"
        ).fetchall() == [(status, 29)]
        assert connection.execute(
            "SELECT total_seconds, sessions_count FROM playtime_totals"
        ).fetchall() == [(29, 1)]
    assert manager._launch_to_session == {}
