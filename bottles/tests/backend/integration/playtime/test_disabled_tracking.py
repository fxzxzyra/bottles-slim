"""Disabled tracking should not write to DB."""

import os
import sqlite3

BOTTLE_ID = "1" * 32



def test_disabled_tracking_smoke(temp_xdg_home, tracker_factory):
    # Use an isolated DB under the temp XDG; instantiate tracker disabled
    base_dir = os.path.join(temp_xdg_home, "bottles")
    os.makedirs(base_dir, exist_ok=True)
    db_path = os.path.join(base_dir, "process_metrics.sqlite")
    tracker = tracker_factory(db_path=db_path, heartbeat_interval=5, enabled=False)
    assert tracker is not None
    assert tracker.enabled is False

    # Attempt to start a session → should be no-op
    sid = tracker.start_session(
        bottle_id=BOTTLE_ID,
        bottle_name="Bottle",
        bottle_path=os.path.join(temp_xdg_home, "bottles", BOTTLE_ID),
        program_name="Game",
        program_path="C:/Game/game.exe",
    )
    assert sid == -1

    # Verify no rows in sessions/totals
    con = sqlite3.connect(tracker.db_path)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM sessions")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM playtime_totals")
    assert cur.fetchone()[0] == 0


