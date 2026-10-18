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
