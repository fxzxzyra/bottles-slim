# taskmanager.py
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

from typing import Optional

from gi.repository import Gio, Gtk

from bottles.backend.models.config import BottleConfig
from bottles.backend.utils.threading import RunAsync
from bottles.backend.wine.winebridge import WineBridge
from bottles.backend.wine.winedbg import WineDbg
from bottles.frontend.utils.columns import TextRow, text_column


@Gtk.Template(resource_path="/com/usebottles/bottles/details-taskmanager.ui")
class TaskManagerView(Gtk.ScrolledWindow):
    __gtype_name__ = "TaskManagerView"

    # region Widgets
    processes_view = Gtk.Template.Child()
    actions = Gtk.Template.Child()
    btn_update = Gtk.Template.Child()
    btn_kill = Gtk.Template.Child()

    # endregion

    def __init__(self, details, config, **kwargs):
        super().__init__(**kwargs)

        # common variables and references
        self.window = details.window
        self.manager = details.window.manager
        self.config = config

        self._generation = 0
        self.processes = Gio.ListStore.new(TextRow)
        self.selection = Gtk.SingleSelection.new(self.processes)
        self.selection.set_autoselect(False)
        self.selection.set_can_unselect(True)
        self.processes_view.set_model(self.selection)
        for index, title in enumerate(("PID", "Name", "Threads")):
            self.processes_view.append_column(text_column(title, index, expand=index == 1))
        self.btn_update.connect("clicked", self.update)
        self.btn_kill.connect("clicked", self.kill_process)
        self.selection.connect("notify::selected-item", self.show_kill_btn)
        self.show_kill_btn()
        self.update(config=config)

    def set_config(self, config):
        self.config = config
        self._generation += 1
        self.processes.remove_all()
        self.btn_update.set_sensitive(True)
        self.show_kill_btn()

    def show_kill_btn(self, *_args):
        self.btn_kill.set_sensitive(self.selection.get_selected_item() is not None)

    def update(self, _widget=None, config: Optional[BottleConfig] = None):
        if config is not None:
            self.config = config
        current = self.config
        self._generation += 1
        generation = self._generation
        self.processes.remove_all()
        self.btn_update.set_sensitive(False)
        self.show_kill_btn()

        def fetch():
            if not current.Runner:
                return []
            bridge = WineBridge(current)
            return bridge.get_procs() if bridge.is_available() else WineDbg(current).get_processes()

        def loaded(processes, error=None):
            if generation != self._generation:
                return
            rows = [] if error or not processes else [
                TextRow((process["pid"], process.get("name", "n/a"), process.get("threads", "0")))
                for process in processes if isinstance(process, dict) and process.get("pid") is not None
            ]
            self.processes.splice(0, self.processes.get_n_items(), rows)
            self.btn_update.set_sensitive(True)
            self.show_kill_btn()

        RunAsync(fetch, loaded)

    def kill_process(self, _widget=None):
        selected = self.selection.get_selected_item()
        if selected is None:
            self.show_kill_btn()
            return
        current = self.config
        generation = self._generation
        self.btn_kill.set_sensitive(False)

        def stop():
            bridge = WineBridge(current)
            if bridge.is_available():
                return bridge.kill_proc(pid=selected.values[0])
            return WineDbg(current).kill_process(pid=selected.values[0])

        def stopped(_result, _error=None):
            if generation == self._generation:
                # Re-read Wine's actual process state even after a failed kill;
                # removing the selected row optimistically hides running apps.
                self.update(config=current)

        RunAsync(stop, stopped)
