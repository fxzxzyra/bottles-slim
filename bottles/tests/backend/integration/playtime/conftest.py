"""Real manager/tracker fixtures with per-test storage and signal ownership."""

from pathlib import Path

import pytest

from bottles.backend.globals import Paths
from bottles.backend.managers.data import DataManager
from bottles.backend.managers.journal import JournalManager
from bottles.backend.managers.manager import Manager
from bottles.backend.managers.playtime import ProcessSessionTracker
from bottles.backend.state import SignalManager
from bottles.backend.utils.singleton import Singleton
from bottles.backend.utils.runners import RunnerRegistry


@pytest.fixture(autouse=True)
def isolated_playtime_state(tmp_path, monkeypatch):
    # Paths are computed at import time: changing only XDG_* would leave the
    # manager, settings and SQLite database pointing at another test's files.
    replacements = {
        Paths.base: str(tmp_path / "data/bottles"),
        Paths.config: str(tmp_path / "config/bottles"),
        Paths.cache: str(tmp_path / "cache/bottles"),
        Paths.state: str(tmp_path / "state/bottles"),
    }
    for name, value in vars(Paths).copy().items():
        if not isinstance(value, str):
            continue
        for old, new in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
            if value == old or value.startswith(old + "/"):
                monkeypatch.setattr(Paths, name, new + value[len(old):])
                break
    for role in ("DATA", "CONFIG", "CACHE", "STATE"):
        location = str(tmp_path / role.lower())
        monkeypatch.setenv(f"XDG_{role}_HOME", location)
        monkeypatch.setattr(Paths, f"xdg_{role.lower()}_home", location)
    Path(Paths.state).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(JournalManager, "path", Paths.journal)
    monkeypatch.setattr(DataManager, "_DataManager__p_data", Paths.user_settings)
    monkeypatch.setattr(Singleton, "_instances", {})
    monkeypatch.setattr(SignalManager, "_SIGNALS", {})
    monkeypatch.setattr(Manager, "_playtime_signals_connected", False)
    monkeypatch.setattr(Manager, "_launch_to_session", {})
    monkeypatch.setattr(Manager, "local_bottles", {})
    monkeypatch.setattr(Paths, "system_runners", ())
    monkeypatch.setattr(RunnerRegistry, "entries", {})
    monkeypatch.setattr(RunnerRegistry, "system", lambda: None)
    yield
    instance = Singleton._instances.get(Manager)
    if instance is not None:
        instance.playtime_tracker.shutdown()
        assert not instance.playtime_tracker._heartbeat_thread.is_alive()


@pytest.fixture
def temp_xdg_home(tmp_path):
    return str(tmp_path / "data")


@pytest.fixture
def test_settings_stub():
    class Settings:
        def get_boolean(self, key):
            return key in ("playtime-enabled", "force-offline")

        def get_int(self, key):
            return 3600 if key == "playtime-heartbeat-interval" else 0

    return Settings()


@pytest.fixture
def manager(test_settings_stub):
    # Keep the real constructor, tracker creation and signal subscriptions.
    # The long heartbeat interval removes wall-clock races in frozen-time tests;
    # dedicated heartbeat tests exercise flushing separately.
    return Manager(g_settings=test_settings_stub, check_connection=False, is_cli=True)


@pytest.fixture
def tracker_factory():
    trackers = []

    def create(**kwargs):
        tracker = ProcessSessionTracker(**kwargs)
        trackers.append(tracker)
        return tracker

    yield create
    for tracker in trackers:
        tracker.shutdown()
        assert not tracker._heartbeat_thread.is_alive()
