# library.py
#
# Copyright 2025 mirkobrombin <brombin94@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, in version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from gettext import gettext as _

from gi.repository import Adw, Gio, GObject, Gtk

from bottles.backend.managers.library import LibraryManager
from bottles.frontend.params import APP_ID
from bottles.frontend.utils.gtk import GtkUtils
from bottles.frontend.widgets.library import LibraryEntry, LibraryEntryInitializationError


def _ordered_library_entries(entries, by_container=False):
    def order(item):
        entry = item[1]
        name = str(entry.get("name") or "").casefold()
        if by_container:
            return str(entry.get("bottle", {}).get("name") or "").casefold(), name
        return name
    return sorted(entries.items(), key=order)


@Gtk.Template(resource_path="/com/usebottles/bottles/library.ui")
class LibraryView(Adw.Bin):
    __gtype_name__ = "LibraryView"

    # region Widgets
    library_stack = Gtk.Template.Child()
    scroll_window = Gtk.Template.Child()
    main_flow = Gtk.Template.Child()
    style_provider = Gtk.CssProvider()
    # endregion

    items_per_line = GObject.property(type=int, default=1, minimum=1)  # type: ignore

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.window = window
        self.settings = Gio.Settings.new(APP_ID)
        self.settings.connect("changed::library-sort-order", lambda *_args: self.update())
        self.css = b""
        self.update()

    def update(self):
        library_manager = LibraryManager()
        entries = library_manager.get_library()

        while self.main_flow.get_first_child() is not None:
            self.main_flow.remove(self.main_flow.get_first_child())

        entry_count = 0
        for u, e in _ordered_library_entries(entries, self.settings.get_uint("library-sort-order") == 1):
            try:
                entry = LibraryEntry(self, u, e)
            except LibraryEntryInitializationError:
                continue
            self.main_flow.append(entry)
            entry_count += 1

        self.library_stack.set_visible_child_name("programs" if entry_count else "empty")
        self.items_per_line = max(entry_count, 1)

    def remove_entry(self, entry):
        previous_items_per_line = self.items_per_line

        @GtkUtils.run_in_main_loop
        def undo_callback(*args):
            self.items_per_line = previous_items_per_line
            entry.show()

        @GtkUtils.run_in_main_loop
        def dismissed_callback(*args):
            self.__delete_entry(entry)

        entry.hide()
        self.items_per_line = max(self.items_per_line - 1, 1)
        self.window.show_toast(
            message=_('"{0}" removed from the library.').format(entry.name),
            timeout=5,
            action_label=_("Undo"),
            action_callback=undo_callback,
            dismissed_callback=dismissed_callback,
        )

    def __delete_entry(self, entry):
        library_manager = LibraryManager()
        library_manager.remove_from_library(entry.library_key, entry.config)
        self.update()

    def go_back(self, widget=False):
        self.window.go_back()
