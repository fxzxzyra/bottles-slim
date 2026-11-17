# rename.py
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

from gi.repository import Adw, Gtk


@Gtk.Template(resource_path="/com/usebottles/bottles/dialog-rename.ui")
class RenameDialog(Adw.Window):
    __gtype_name__ = "RenameDialog"

    # region Widgets
    entry_name = Gtk.Template.Child()
    btn_cancel = Gtk.Template.Child()
    btn_save = Gtk.Template.Child()

    # endregion

    def __init__(self, window, name, on_save, **kwargs):
        super().__init__(**kwargs)

        self.set_transient_for(window)

        # common variables and references
        self.window = window
        self.manager = window.manager
        self.on_save = on_save

        # set widget defaults
        self.entry_name.set_text(name)
        self.original_name = name

        # connect signals
        self.entry_name.connect("changed", self.on_change)
        self.entry_name.connect("entry-activated", self.__on_save)
        self.on_change()
        self.btn_cancel.connect("clicked", self.__close_window)
        self.btn_save.connect("clicked", self.__on_save)

    def __on_save(self, *_args):
        text = self.entry_name.get_text().strip()
        if not text or text == self.original_name:
            return
        self.on_save(new_name=text)
        self.destroy()

    def __close_window(self, *_args):
        self.destroy()

    def on_change(self, *_args):
        text = self.entry_name.get_text().strip()
        self.btn_save.set_sensitive(bool(text) and text != self.original_name)
