"""Check blocking/release/reset behavior without millisecond scheduling claims."""

from concurrent.futures import Future, TimeoutError
from enum import Enum
from threading import Event, Thread

import pytest

from bottles.backend.state import EventManager


class Events(Enum):
    FIRST = "first.event"
    SECOND = "second.event"


@pytest.fixture
def waiters(monkeypatch):
    monkeypatch.setattr(EventManager, "_EVENTS", {})
    threads = []

    def start(event):
        entered = Event()
        result = Future()

        def wait():
            entered.set()
            try:
                EventManager.wait(event)
            except BaseException as error:
                result.set_exception(error)
            else:
                result.set_result(None)

        thread = Thread(target=wait, daemon=True)
        threads.append(thread)
        thread.start()
        assert entered.wait(5), "Worker did not start"
        return result

    yield start
    # Release the underlying primitives even if done/reset is the broken code.
    for event in EventManager._EVENTS.values():
        event.set()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive(), "Event waiter leaked out of its test"


def assert_blocked(result):
    with pytest.raises(TimeoutError):
        result.result(timeout=0.05)


def test_wait_blocks_until_matching_done(waiters):
    result = waiters(Events.FIRST)
    assert_blocked(result)
    EventManager.done(Events.FIRST)
    assert result.result(timeout=5) is None


def test_done_before_wait_is_not_lost(waiters):
    EventManager.done(Events.FIRST)
    assert waiters(Events.FIRST).result(timeout=5) is None


def test_reset_rearms_event_for_next_waiter(waiters):
    EventManager.done(Events.FIRST)
    assert waiters(Events.FIRST).result(timeout=5) is None
    EventManager.reset(Events.FIRST)
    result = waiters(Events.FIRST)
    assert_blocked(result)
    EventManager.done(Events.FIRST)
    assert result.result(timeout=5) is None


def test_done_releases_all_waiters_for_same_enum_value(waiters):
    results = [waiters(Events.FIRST), waiters(Events("first.event")), waiters(Events.FIRST)]
    for result in results:
        assert_blocked(result)
    EventManager.done(Events.FIRST)
    assert [result.result(timeout=5) for result in results] == [None, None, None]
    assert len(EventManager._EVENTS) == 1


def test_different_events_do_not_release_each_other(waiters):
    first = waiters(Events.FIRST)
    second = waiters(Events.SECOND)
    assert_blocked(first)
    assert_blocked(second)
    EventManager.done(Events.FIRST)
    assert first.result(timeout=5) is None
    assert_blocked(second)
    EventManager.done(Events.SECOND)
    assert second.result(timeout=5) is None


def test_repeated_done_and_reset_preserve_one_event(waiters):
    EventManager.done(Events.FIRST)
    EventManager.done(Events.FIRST)
    assert waiters(Events.FIRST).result(timeout=5) is None
    EventManager.reset(Events.FIRST)
    EventManager.reset(Events.FIRST)
    result = waiters(Events.FIRST)
    assert_blocked(result)
    assert len(EventManager._EVENTS) == 1
    EventManager.done(Events.FIRST)
    assert result.result(timeout=5) is None
