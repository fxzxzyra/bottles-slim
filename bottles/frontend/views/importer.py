# importer.py
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

from gi.repository import Adw, Gio, GLib, Gtk

from bottles.backend.managers.backup import BackupManager
from bottles.backend.state import SignalManager, Signals, TaskManager
from bottles.backend.utils.threading import RunAsync
from bottles.frontend.utils.gtk import GtkUtils
from bottles.frontend.utils.flatpak import resolve_bottles_directory


@Gtk.Template(resource_path="/com/usebottles/bottles/importer.ui")
class ImporterView(Adw.Bin):
    __gtype_name__ = "ImporterView"

    # region Widgets
    btn_import_config = Gtk.Template.Child()
    btn_import_full = Gtk.Template.Child()
    btn_back = Gtk.Template.Child()
    btn_import_existing = Gtk.Template.Child()
    box_import_progress = Gtk.Template.Child()
    spinner_import = Gtk.Template.Child()
    label_import_progress = Gtk.Template.Child()

    # endregion

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)

        # common variables and references
        self.window = window
        self.manager = window.manager
        self.import_manager = window.manager.import_manager

        # connect signals
        self.btn_back.connect("clicked", self.go_back)
        self.btn_import_existing.connect("clicked", self.__import_existing)
        self.btn_import_full.connect("clicked", self.__import_full_bck)
        self.btn_import_config.connect("clicked", self.__import_config_bck)

        # Import progress tracking
        self._import_task_id = None
        SignalManager.connect(Signals.TaskAdded, self._on_task_added)
        SignalManager.connect(Signals.TaskRemoved, self._on_task_removed)
        SignalManager.connect(Signals.TaskUpdated, self._on_task_updated)

    def __import_existing(self, *_args):
        def selected(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return
            path = resolve_bottles_directory(self.window, folder.get_path())
            if path:
                RunAsync(self.import_manager.import_bottle, callback=self.__finish, path=path)
        dialog = Gtk.FileDialog(title=_("Select an Existing Container"), modal=True)
        dialog.select_folder(self.window, None, selected)

    def __restore_backup(self, scope, source):
        def selected(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return
            destination = resolve_bottles_directory(self.window, folder.get_path())
            if destination:
                RunAsync(BackupManager.import_backup, callback=self.__finish,
                         scope=scope, path=source, destination=destination)
        dialog = Gtk.FileDialog(title=_("Select an Empty Container Directory"), modal=True)
        dialog.select_folder(self.window, None, selected)

    @GtkUtils.run_in_main_loop
    def __finish(self, result, error=False):
        if not error and result is not None and result.ok:
            self.window.show_toast(_("Container imported successfully"))
            self.window.page_list.update_bottles_list()
        else:
            self.window.show_toast(str(error) if error else (result.message if result else "") or _("Import failed"))

    def __import_full_bck(self, *_args):
        self.__choose_backup("full")

    def __import_config_bck(self, *_args):
        self.__choose_backup("config")

    def __choose_backup(self, scope):
        full = scope == "full"
        filters = Gio.ListStore.new(Gtk.FileFilter)
        supported = Gtk.FileFilter(name="tar.gz" if full else "YAML")
        for pattern in (["*.tar.gz"] if full else ["*.yml", "*.yaml"]):
            supported.add_pattern(pattern)
        filters.append(supported)
        all_files = Gtk.FileFilter(name=_("All Files"))
        all_files.add_pattern("*")
        filters.append(all_files)

        def selected(dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            self.__restore_backup(scope, file.get_path())

        dialog = Gtk.FileDialog(
            title=_("Select a Backup Archive") if full else _("Select a Configuration File"),
            accept_label=_("Import"), filters=filters, modal=True,
        )
        dialog.open(self.window, None, selected)

    def _on_task_added(self, data=None):
        """Signal handler for TaskAdded events. Shows progress if import task."""
        if not data or not data.data:
            return

        task_id = data.data
        task = TaskManager.get(task_id)
        if not task:
            return

        # Check if this is an import task
        if task.kind == "import":
            self._import_task_id = task_id
            GLib.idle_add(self._show_import_progress)

    def _on_task_removed(self, data=None):
        """Signal handler for TaskRemoved events. Hides progress if import task."""
        if not data or not data.data:
            return

        task_id = data.data
        if task_id == self._import_task_id:
            self._import_task_id = None
            GLib.idle_add(self._hide_import_progress)

    def _on_task_updated(self, data=None):
        """Signal handler for TaskUpdated events. Updates progress label."""
        if not data or not data.data:
            return

        task_id = data.data
        if task_id == self._import_task_id:
            task = TaskManager.get(task_id)
            if task and task.subtitle:
                GLib.idle_add(self._update_import_progress, task.subtitle)

    def _show_import_progress(self):
        """Show the import progress indicator."""
        self.label_import_progress.set_text(_("Restoring Backup…"))
        self.box_import_progress.set_visible(True)
        self.spinner_import.start()

    def _hide_import_progress(self):
        """Hide the import progress indicator."""
        self.spinner_import.stop()
        self.box_import_progress.set_visible(False)

    def _update_import_progress(self, text: str):
        """Update the import progress label."""
        self.label_import_progress.set_text(text)

    def go_back(self, *_args):
        self.window.go_back()
