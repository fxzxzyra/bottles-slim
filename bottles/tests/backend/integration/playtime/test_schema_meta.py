"""Schema meta assertions: indices and PRAGMA user_version.
"""

import sqlite3
from pathlib import Path

from bottles.backend.globals import Paths

BOTTLE_ID = "1" * 32


def test_schema_meta_smoke(manager):
    assert Path(manager.get_playtime_tracker(BOTTLE_ID).db_path).parent == Path(manager.local_bottles[BOTTLE_ID].Path)
    assert not (Path(Paths.base) / "process_metrics.sqlite").exists()
    con = sqlite3.connect(manager.get_playtime_tracker(BOTTLE_ID).db_path)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indices = {r[0] for r in cur.fetchall()}
    assert "idx_sessions_bottle_program" in indices
    assert "idx_sessions_status" in indices
    assert "idx_totals_last_played" in indices
    cur.execute("PRAGMA user_version")
    assert cur.fetchone()[0] == 1
