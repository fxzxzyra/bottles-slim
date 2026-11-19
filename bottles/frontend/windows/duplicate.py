# duplicate.py
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

from gi.repository import Adw, GLib, Gtk

from bottles.backend.managers.backup import BackupManager
from bottles.backend.utils.threading import RunAsync
from bottles.frontend.utils.gtk import GtkUtils
from bottles.frontend.utils.flatpak import resolve_bottles_directory


@Gtk.Template(resource_path="/com/usebottles/bottles/dialog-duplicate.ui")
class DuplicateDialog(Adw.Dialog):
    __gtype_name__ = "DuplicateDialog"

    # region Widgets
    entry_name = Gtk.Template.Child()
    btn_cancel = Gtk.Template.Child()
    btn_duplicate = Gtk.Template.Child()
    stack_switcher = Gtk.Template.Child()
    spinner = Gtk.Template.Child()
    page_failed = Gtk.Template.Child()

    # endregion

    def __init__(self, parent, **kwargs):
        super().__init__(**kwargs)

        # common variables and references
        self.parent = parent
        self.config = parent.config

        self.entry_name.connect("changed", self.__check_entry_name)

        # connect signals
        self.btn_duplicate.connect("clicked", self.__duplicate_bottle)
        self.btn_cancel.connect("clicked", lambda _button: self.close())

    def __check_entry_name(self, *_args):
        name = self.entry_name.get_text().strip()
        is_invalid = not name or any(config.Name == name for config in self.parent.manager.local_bottles.values())
        if is_invalid:
            self.entry_name.add_css_class("error")
            self.btn_duplicate.set_sensitive(False)
        else:
            self.entry_name.remove_css_class("error")
            self.btn_duplicate.set_sensitive(True)

    def __duplicate_bottle(self, widget):
        """Choose the destination and keep the dialog open until copying finishes."""
        def selected(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return
            destination = resolve_bottles_directory(self.parent.window, folder.get_path())
            if not destination:
                return
            self.stack_switcher.set_visible_child_name("page_duplicating")
            self.btn_duplicate.set_visible(False)
            self.set_can_close(False)
            self.btn_cancel.set_sensitive(False)
            self.btn_cancel.set_label(_("Close"))
            self.spinner.start()
            RunAsync(BackupManager.duplicate_bottle, callback=self.finish,
                     config=self.config, name=self.entry_name.get_text().strip(), destination=destination)
        dialog = Gtk.FileDialog(title=_("Select an Empty Container Directory"), modal=True)
        dialog.select_folder(self.parent.window, None, selected)

    @GtkUtils.run_in_main_loop
    def finish(self, result, error=None):
        self.spinner.stop()
        self.set_can_close(True)
        self.btn_cancel.set_sensitive(True)
        self.btn_cancel.set_label(_("Close"))

        if error or result is None or not result.status:
            message = str(error) if error else result.message if result else ""
            self.page_failed.set_description(
                message or _("The container could not be duplicated.")
            )
            self.stack_switcher.set_visible_child_name("page_failed")
            return

        self.parent.manager.update_bottles()
        self.stack_switcher.set_visible_child_name("page_duplicated")
