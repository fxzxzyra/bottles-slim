# bottle_installers.py
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

from bottles.backend.models.result import Result
from bottles.backend.utils.threading import RunAsync
from bottles.frontend.utils.common import open_doc_url
from bottles.frontend.widgets.installer import InstallerEntry


@Gtk.Template(resource_path="/com/usebottles/bottles/details-installers.ui")
class InstallersView(Adw.Bin):
    __gtype_name__ = "DetailsInstallers"

    # region Widgets
    list_installers = Gtk.Template.Child()
    btn_help = Gtk.Template.Child()
    btn_toggle_search = Gtk.Template.Child()
    entry_search = Gtk.Template.Child()
    search_bar = Gtk.Template.Child()
    actions = Gtk.Template.Child()
    pref_page = Gtk.Template.Child()
    status_page = Gtk.Template.Child()

    # endregion

    def __init__(self, details, config, **kwargs):
        super().__init__(**kwargs)

        # common variables and references
        self.window = details.window
        self.manager = details.window.manager
        self.config = config
        self.__registry = []
        self.__update_generation = 0
        self.ev_controller = Gtk.EventControllerKey.new()

        self.ev_controller.connect("key-released", self.__search_installers)
        self.entry_search.add_controller(self.ev_controller)

        self.search_bar.set_key_capture_widget(self.window)
        self.btn_help.connect("clicked", open_doc_url, "bottles/installers")
        self.entry_search.connect("changed", self.__search_installers)

    def __search_installers(self, *_args):
        """
        This function search in the list of installers the
        text written in the search entry.
        """
        terms = self.entry_search.get_text()
        self.list_installers.set_filter_func(self.__filter_installers, terms)

    @staticmethod
    def __filter_installers(row, terms=None):
        text = (row.get_title() or "") + (row.get_subtitle() or "")
        return (terms or "").casefold() in text.casefold()

    def empty_list(self):
        for r in self.__registry:
            if r.get_parent() is not None:
                r.get_parent().remove(r)
        self.__registry = []

    def update(self, widget=False, config=None):
        """
        This function update the installers list with the
        supported by the manager.
        """
        if config is None:
            config = self.config
        self.config = config
        self.__update_generation += 1
        generation = self.__update_generation
        include_unstable = self.window.settings.get_boolean("release-candidate")
        self.list_installers.set_sensitive(False)

        def callback(result, error=False):
            if generation != self.__update_generation:
                return
            self.empty_list()
            available = not error and isinstance(result, Result) and result.ok
            entries = result.data["entries"] if available else []
            if available:
                self.manager.supported_installers = result.data["catalog"]
                for installer in entries:
                    entry = InstallerEntry(
                        window=self.window, config=config, installer=installer
                    )
                    self.list_installers.append(entry)
                    self.__registry.append(entry)
            self.status_page.set_visible(not entries)
            self.pref_page.set_visible(bool(entries))
            self.list_installers.set_visible(bool(entries))
            self.list_installers.set_sensitive(True)

        def process_installers():
            catalog = self.manager.installer_manager.refresh_catalog()
            if not catalog:
                catalog = self.manager.supported_installers
            entries = []
            for name, metadata in catalog.items():
                if not isinstance(metadata, dict):
                    continue
                installer = (name, metadata)
                if metadata.get("Arch", "win64") != config.Arch:
                    continue
                if not self.manager.installer_manager.supports_channel(
                    installer, include_unstable
                ):
                    continue
                entries.append(installer)
            return Result(True, data={"entries": entries, "catalog": catalog})

        RunAsync(process_installers, callback)
