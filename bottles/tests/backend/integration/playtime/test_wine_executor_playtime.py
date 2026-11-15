"""Exercise executor -> real signals -> real manager -> persisted SQLite totals."""

import sqlite3

import pytest
from freezegun import freeze_time

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.wine.executor import WineExecutor


@pytest.mark.parametrize("outcome", ["success", "failure", "exception"])
def test_executor_persists_launch_outcome(manager, tmp_path, mocker, outcome):
    config = manager.local_bottles["b1"]
    executor = WineExecutor(config=config, exec_path="C:/Office/editor.exe")
    # Conversion is real and must not turn a forward-slash Windows path into
    # an empty working directory. Only the actual Wine launch is substituted.
    assert executor.cwd == str(tmp_path / "prefix/dosdevices/c:/Office")

    with freeze_time("2025-01-01 12:00:00") as clock:
        def launch(_executor):
            clock.tick(37)
            if outcome == "exception":
                raise OSError("Wine launch failed")
            return Result(outcome == "success", data={"output": b"ok"})

        boundary = mocker.patch.object(
            WineExecutor, "_WineExecutor__launch_with_bridge",
            autospec=True, side_effect=launch,
        )
        if outcome == "exception":
            with pytest.raises(OSError, match="Wine launch failed"):
                executor.run()
        else:
            assert executor.run().ok is (outcome == "success")
        boundary.assert_called_once_with(executor)

    expected_status = "success" if outcome == "success" else "unknown"
    with sqlite3.connect(manager.get_playtime_tracker("b1").db_path) as connection:
        assert connection.execute(
            "SELECT bottle_id, program_path, status, duration_seconds FROM sessions"
        ).fetchall() == [("b1", r"C:\Office\editor.exe", expected_status, 37)]
        assert connection.execute(
            "SELECT bottle_id, total_seconds, sessions_count FROM playtime_totals"
        ).fetchall() == [("b1", 37, 1)]
    assert manager._launch_to_session == {}
