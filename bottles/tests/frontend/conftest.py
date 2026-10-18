"""Frontend tests use the resources built for this checkout, independently of /app."""

import os
from pathlib import Path

import gi
import pytest

for namespace, version in (("Gtk", "4.0"), ("Adw", "1"), ("GtkSource", "5"),
                           ("Xdp", "1.0"), ("XdpGtk4", "1.0")):
    gi.require_version(namespace, version)

from gi.repository import Adw, Gio  # noqa: E402

for variable in ("BOTTLES_TEST_RESOURCE", "BOTTLES_TEST_DATA_RESOURCE"):
    filename = os.environ.get(variable)
    if not filename or not Path(filename).is_file():
        raise pytest.UsageError(f"{variable} must point to a built resource; use meson test -C build with -Dtests=true")
    Gio.resources_register(Gio.Resource.load(filename))

Adw.init()


@pytest.fixture(autouse=True)
def fail_on_gtk_callback_exception(monkeypatch):
    """PyGObject reports callback exceptions to excepthook instead of raising."""
    import sys
    import traceback

    from bottles.backend.globals import Paths

    Path(Paths.state).mkdir(parents=True, exist_ok=True)
    errors = []
    monkeypatch.setattr(
        sys, "excepthook",
        lambda kind, value, tb: errors.append("".join(traceback.format_exception(kind, value, tb))),
    )
    yield
    assert not errors, "Unhandled GTK callback exception:\n" + "\n".join(errors)


@pytest.fixture
def iterate_until():
    """Dispatch real GLib sources; bound waits instead of guessing a sleep."""
    import time
    from gi.repository import GLib

    def iterate(predicate, timeout=5):
        context = GLib.MainContext.default()
        deadline = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < deadline, "GLib condition did not become true"
            context.iteration(False)
            time.sleep(0.001)

    return iterate
