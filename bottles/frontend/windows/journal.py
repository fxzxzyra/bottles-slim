# journal.py
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

from datetime import datetime
from gettext import gettext

from gi.repository import Adw, Gio, GLib, Gtk

from bottles.backend.managers.journal import JournalManager, JournalSeverity
from bottles.frontend.utils.columns import TextRow, text_column


@Gtk.Template(resource_path="/com/usebottles/bottles/dialog-journal.ui")
class JournalDialog(Adw.Window):
    __gtype_name__ = "JournalDialog"

    # region Widgets
    journal_view = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    btn_all = Gtk.Template.Child()
    btn_critical = Gtk.Template.Child()
    btn_error = Gtk.Template.Child()
    btn_warning = Gtk.Template.Child()
    btn_info = Gtk.Template.Child()
    label_filter = Gtk.Template.Child()

    # endregion

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.journal = list(JournalManager.get(period="all").items())
        self.store = Gio.ListStore.new(TextRow)
        self.current_severity = ""

        # connect signals
        self.search_entry.connect("search-changed", self.on_search_changed)
        self.btn_all.connect("clicked", self.filter_results, "")
        self.btn_critical.connect(
            "clicked", self.filter_results, JournalSeverity.CRITICAL
        )
        self.btn_error.connect("clicked", self.filter_results, JournalSeverity.ERROR)
        self.btn_warning.connect(
            "clicked", self.filter_results, JournalSeverity.WARNING
        )
        self.btn_info.connect("clicked", self.filter_results, JournalSeverity.INFO)

        self.journal_view.set_model(Gtk.NoSelection.new(self.store))
        for index, title in enumerate((gettext("Severity"), gettext("Timestamp"), gettext("Message"))):
            self.journal_view.append_column(text_column(title, index, expand=index == 2, markup=index < 2))
        self.populate()

    def populate(self, query="", severity=None):
        self.store.remove_all()

        if severity is None:
            severity = self.current_severity

        colors = {
            JournalSeverity.CRITICAL: "#db1600",
            JournalSeverity.ERROR: "#db6600",
            JournalSeverity.WARNING: "#dba100",
            JournalSeverity.INFO: "#3283a8",
            JournalSeverity.CRASH: "#db1600",
        }

        last_date_label = None

        for _, value in self.journal:
            if query.casefold() not in (value.get("message") or "").casefold():
                continue

            if severity not in ("", value["severity"]):
                continue

            timestamp = value.get("timestamp") or ""
            try:
                timestamp_dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                date_label = timestamp_dt.strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                date_label = ""

            if date_label != last_date_label:
                self.store.append(TextRow(("", f"<b>{GLib.markup_escape_text(date_label)}</b>", "")))
                last_date_label = date_label

            self.store.append(
                TextRow((
                    '<span foreground="{}"><b>{}</b></span>'.format(
                        colors.get(
                            value["severity"],
                            colors.get(JournalSeverity.INFO, "#3283a8"),
                        ),
                        GLib.markup_escape_text(value["severity"].capitalize()),
                    ),
                    GLib.markup_escape_text(timestamp),
                    value.get("message") or "",
                ))
            )

    def on_search_changed(self, entry):
        self.populate(entry.get_text())

    def filter_results(self, _, severity):
        self.current_severity = severity
        self.populate(self.search_entry.get_text())

        severity_labels = {
            JournalSeverity.CRITICAL: gettext("Critical"),
            JournalSeverity.ERROR: gettext("Errors"),
            JournalSeverity.WARNING: gettext("Warnings"),
            JournalSeverity.INFO: gettext("Info"),
            JournalSeverity.CRASH: gettext("Crashes"),
        }

        label = severity_labels.get(severity, gettext("All messages"))
        self.label_filter.set_text(label)
