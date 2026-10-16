# ruff: noqa: E402

from types import SimpleNamespace

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GLib, Gtk


from bottles.backend.models.config import BottleConfig
from bottles.frontend.views.bottle_versioning import VersioningView


def test_empty_snapshot_page_is_visible():
    config = BottleConfig()
    config.Versioning = True
    details = SimpleNamespace(
        window=SimpleNamespace(
            manager=SimpleNamespace(versioning_manager=object()),
        ),
    )
    view = VersioningView(details, config)
    view.status_page.set_visible(True)
    view.pref_page.set_visible(False)
    window = Gtk.Window(child=view)
    window.set_default_size(640, 480)
    window.present()

    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)

    assert isinstance(view, Adw.Bin)
    assert view.status_page.get_mapped()
    assert view.status_page.get_width() > 0
    assert view.status_page.get_height() > 0
    window.destroy()
