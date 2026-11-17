# new_bottle_dialog.py
#
# Copyright 2025 The Bottles Contributors
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
from threading import Event
from typing import Any, Optional

from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango

from bottles.backend.models.config import BottleConfig
from bottles.backend.models.result import Result
from bottles.backend.state import Task, TaskManager
from bottles.backend.utils.threading import RunAsync
from bottles.frontend.utils.common import format_runner_name
from bottles.frontend.utils.flatpak import resolve_bottles_directory
from bottles.frontend.utils.gtk import GtkUtils


@Gtk.Template(resource_path="/com/usebottles/bottles/check-row.ui")
class BottlesCheckRow(Adw.ActionRow):
    """An `AdwActionRow` with a designated `GtkCheckButton` as prefix."""

    __gtype_name__ = "BottlesCheckRow"

    check_button = Gtk.Template.Child()

    active = GObject.Property(type=bool, default=False)
    environment = GObject.Property(type=str, default=None)

    # Add row’s check button to the group
    group = GObject.Property(
        # FIXME: Supposed to be a BottlesCheckRow widget type.
        type=Adw.ActionRow,
        default=None,
        setter=lambda self, group: self.check_button.set_group(group.check_button),
    )


@Gtk.Template(resource_path="/com/usebottles/bottles/new-bottle-dialog.ui")
class BottlesNewBottleDialog(Adw.Dialog):
    __gtype_name__ = "BottlesNewBottleDialog"

    # region Widgets
    entry_name = Gtk.Template.Child()
    stack_create = Gtk.Template.Child()
    btn_create = Gtk.Template.Child()
    btn_cancel = Gtk.Template.Child()
    btn_close = Gtk.Template.Child()
    btn_choose_env = Gtk.Template.Child()
    btn_choose_env_reset = Gtk.Template.Child()
    label_choose_env = Gtk.Template.Child()
    status_page_status = Gtk.Template.Child()
    btn_choose_path = Gtk.Template.Child()
    btn_choose_path_reset = Gtk.Template.Child()
    label_choose_path = Gtk.Template.Child()
    steps_list = Gtk.Template.Child()
    scrolled_steps = Gtk.Template.Child()
    btn_cancel_creating = Gtk.Template.Child()
    combo_runner = Gtk.Template.Child()
    btn_manage_runners = Gtk.Template.Child()
    combo_arch = Gtk.Template.Child()
    str_list_arch = Gtk.Template.Child()
    str_list_runner = Gtk.Template.Child()
    menu_duplicate = Gtk.Template.Child()
    environment_list_box = Gtk.Template.Child()
    switch_sandbox = Gtk.Template.Child()

    selected_environment = GObject.Property(type=str, default=None)

    # endregion

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.combo_runner.set_list_factory(
            GtkUtils.create_full_width_string_list_factory()
        )
        # common variables and references
        self.window = GtkUtils.get_parent_window()
        if not self.window:
            return

        self.app = self.window.get_application()
        self.manager = self.window.manager
        self.new_bottle_config = BottleConfig()
        self.env_recipe_path = None
        self.custom_path = ""
        self.runner = None
        self.default_string = _("(Default)")

        self._creation_task: Optional[Task] = None
        self._creation_job: Optional[RunAsync] = None
        self._creation_cancel_event: Optional[Event] = None
        self._cancel_requested = False
        self._creation_steps: list[Adw.ActionRow] = []

        self.arch = {"win64": "64-bit", "win32": "32-bit"}

        # connect signals
        self.window.connect("notify::is-active", self.__remove_notifications)
        self.btn_cancel.connect("clicked", self.__close_dialog)
        self.btn_close.connect("clicked", self.__close_dialog)
        self.btn_create.connect("clicked", self.create_bottle)
        self.btn_cancel_creating.connect("clicked", self.__prompt_cancel_confirmation)
        self.btn_choose_env.connect("clicked", self.__choose_env_recipe)
        self.btn_choose_env_reset.connect("clicked", self.__reset_env_recipe)
        self.btn_choose_path.connect("clicked", self.__choose_path)
        self.btn_choose_path_reset.connect("clicked", self.__reset_path)
        self.btn_manage_runners.connect("clicked", self.__manage_runners)
        self.combo_runner.connect("notify::selected", self.__check_entry_name)
        self.entry_name.connect("changed", self.__check_entry_name)
        self.entry_name.connect("entry-activated", self.__entry_activated)
        self.environment_list_box.connect(
            "row-activated",
            lambda _, row: self.set_property("selected-environment", row.environment),
        )

        # Populate widgets
        self.label_choose_env.set_label(self.default_string)
        self.label_choose_path.set_label(_("Select an empty directory"))
        self._runner_ids = []
        self.__refresh_runners()
        self.str_list_arch.splice(0, 0, list(self.arch.values()))

        self.selected_environment = (
            self.environment_list_box.get_first_child().environment
        )

    def __refresh_runners(self) -> None:
        selected = self.combo_runner.get_selected()
        previous = self._runner_ids[selected] if selected < len(self._runner_ids) else None
        self._runner_ids = list(self.manager.runners_available)
        self.str_list_runner.splice(
            0, self.str_list_runner.get_n_items(),
            [format_runner_name(r) for r in self._runner_ids],
        )
        if previous in self._runner_ids:
            self.combo_runner.set_selected(self._runner_ids.index(previous))
        self.combo_runner.set_subtitle(
            _("Choose the Wine installation used by this bottle") if self._runner_ids
            else _("Register a runner in Preferences before creating a bottle")
        )
        self.__check_entry_name()

    def __manage_runners(self, *_args: Any) -> None:
        dialog = self.window.show_runners_preferences_view()

        def closed(_dialog):
            dialog.disconnect(handler)
            self.__refresh_runners()

        handler = dialog.connect("closed", closed)

    def __check_validity(self, *_args: Any) -> tuple[bool, bool]:
        is_empty = not self.entry_name.get_text().strip()
        is_duplicate = self.entry_name.get_text() in self.manager.local_bottles
        return (is_empty, is_duplicate)

    def __check_entry_name(self, *_args: Any) -> None:
        is_empty, is_duplicate = self.__check_validity()
        is_invalid = is_empty or is_duplicate
        runner_selected = self.combo_runner.get_selected() < len(self._runner_ids)
        self.btn_create.set_sensitive(not is_invalid and bool(self.custom_path) and runner_selected)
        self.menu_duplicate.set_visible(is_duplicate)

        if is_invalid:
            self.entry_name.add_css_class("error")
        else:
            self.entry_name.remove_css_class("error")

    def __entry_activated(self, *_args: Any) -> None:
        self.create_bottle()

    def __remove_notifications(self, *_args: Any) -> None:
        self.app.withdraw_notification("bottle-created-completed")

    def __choose_env_recipe(self, *_args: Any) -> None:
        """
        Opens a file chooser dialog to select the configuration file
        in yaml format.
        """

        def set_path(dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return

            self.btn_choose_env_reset.set_visible(True)
            self.env_recipe_path = file.get_path()
            self.label_choose_env.set_label(file.get_basename())
            self.label_choose_env.set_ellipsize(Pango.EllipsizeMode.MIDDLE)

        filters = Gio.ListStore.new(Gtk.FileFilter)

        yaml_filter = Gtk.FileFilter()
        yaml_filter.set_name("YAML")
        yaml_filter.add_mime_type("application/yaml")

        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All Files"))
        all_filter.add_pattern("*")

        filters.append(yaml_filter)
        filters.append(all_filter)

        dialog = Gtk.FileDialog.new()
        dialog.set_title(_("Select Configuration"))
        dialog.set_filters(filters)

        dialog.open(self.window, callback=set_path)

    def __choose_path(self, *_args: Any) -> None:
        """Opens a file chooser dialog to select the directory."""

        def set_path(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return

            path = resolve_bottles_directory(self.window, folder.get_path())
            if path is None:
                return

            self.custom_path = path
            self.__check_entry_name()

            self.btn_choose_path_reset.set_visible(True)
            self.label_choose_path.set_label(path)
            self.btn_choose_path.set_tooltip_text(path)
            self.label_choose_path.set_ellipsize(Pango.EllipsizeMode.MIDDLE)

        dialog = Gtk.FileDialog.new()
        dialog.set_title(_("Select Directory"))
        dialog.set_modal(True)
        dialog.select_folder(parent=self.window, callback=set_path)

    def create_bottle(self, *_args: Any) -> None:
        """Starts creating the bottle."""
        if not self.custom_path or any(self.__check_validity()):
            return
        runner_index = self.combo_runner.get_selected()
        if runner_index >= len(self._runner_ids):
            return
        self.runner = self._runner_ids[runner_index]
        # set widgets states
        self.set_can_close(False)
        self.stack_create.set_visible_child_name("page_creating")
        self._cancel_requested = False
        self.__reset_creation_steps()
        self.btn_cancel_creating.set_sensitive(True)
        self.btn_cancel_creating.set_label(_("_Cancel Creation"))

        self.__clear_creation_task()

        task_title = _("Creating “{0}”").format(self.entry_name.get_text())
        self._creation_task = Task(title=task_title)
        TaskManager.add(self._creation_task)

        self._creation_cancel_event = Event()
        self._creation_job = RunAsync(
            task_func=self.manager.create_bottle,
            callback=self.finish,
            name=self.entry_name.get_text(),
            path=self.custom_path,
            environment=self.selected_environment,
            runner=self.runner,
            arch=list(self.arch)[self.combo_arch.get_selected()],
            dxvk=self.manager.dxvk_available[0] if self.manager.dxvk_available else False,
            sandbox=self.switch_sandbox.get_active(),
            fn_logger=self.update_output,
            custom_environment=self.env_recipe_path,
            cancel_event=self._creation_cancel_event,
        )

    @GtkUtils.run_in_main_loop
    def update_output(self, text: str) -> None:
        """
        Updates the creation progress list with the given text.
        """
        new_line = text.rstrip("\n")

        if not new_line.strip():
            return

        self.__mark_last_step_completed()

        row = self.__create_step_row(new_line)
        self.steps_list.append(row)
        self._creation_steps.append(row)

        def _scroll_to_bottom():
            adj = self.scrolled_steps.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
            return False

        GLib.idle_add(_scroll_to_bottom)

        adjustment = self.scrolled_steps.get_vadjustment()
        new_value = adjustment.get_upper() - adjustment.get_page_size()
        adjustment.set_value(max(new_value, adjustment.get_lower()))

        if self._creation_task is not None:
            self._creation_task.subtitle = new_line.strip()

    def __create_step_row(self, text: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=text)
        row.set_activatable(False)
        row.set_selectable(False)

        check_image = Gtk.Image.new_from_icon_name("selection-mode-symbolic")
        check_image.add_css_class("accent")
        check_image.set_visible(False)

        row.add_suffix(check_image)
        row._completion_icon = check_image  # type: ignore[attr-defined]

        return row

    def __mark_last_step_completed(self) -> None:
        if not self._creation_steps:
            return

        self.__set_step_completed(self._creation_steps[-1])

    def __set_step_completed(self, row: Adw.ActionRow) -> None:
        icon = getattr(row, "_completion_icon", None)
        if icon:
            icon.set_visible(True)

    @GtkUtils.run_in_main_loop
    def finish(self, result: Optional[Result], error=None) -> None:
        """Updates widgets based on whether it succeeded or failed."""

        def send_notification(notification: Gio.Notification) -> None:
            """Sends notification if out of focus."""
            if not self.window.is_active():
                self.app.send_notification("bottle-created-completed", notification)

        result_config = None
        if result and result.data:
            result_config = result.data.get("config")
            if result_config:
                self.new_bottle_config = result_config

        self.__mark_last_step_completed()

        if self._cancel_requested and result and result.message == "cancelled":
            self.__clear_creation_task()
            self.set_can_close(True)
            self.__finalize_close()
            return

        self.set_can_close(True)
        self.stack_create.set_visible_child_name("page_completed")
        notification = Gio.Notification()

        self.__clear_creation_task()

        # Show error if bottle unsuccessfully builds
        if not result or not result.status or error:
            title = _("Unable to Create Bottle")
            notification.set_title(title)
            message = str(error) if error else ((result.message if result else "") or _("Bottle creation failed."))
            notification.set_body(message)
            self.status_page_status.set_description(message)
            self.status_page_status.set_title(title)
            self.btn_close.add_css_class("destructive-action")
            send_notification(notification)

            # Display error logs in the result page
            self.__mark_last_step_completed()
            self.scrolled_steps.unparent()
            box = self.status_page_status.get_child()
            box.prepend(self.scrolled_steps)

            return

        # Show success
        title = _("Bottle Created")
        description = _("“{0}” was created successfully.").format(
            self.entry_name.get_text()
        )

        notification.set_title(title)
        notification.set_body(description)

        self.new_bottle_config = result.data.get("config")
        self.btn_close.add_css_class("suggested-action")
        self.status_page_status.set_icon_name("selection-mode-symbolic")
        self.status_page_status.set_title(title)
        self.status_page_status.set_description(description)
        send_notification(notification)

        # Ask the manager to check for new bottles,
        # then update the user bottles' list.
        self.manager.check_bottles()
        self.window.page_list.update_bottles_list()
        self.window.page_list.show_page(self.new_bottle_config.Name)

    def __reset_env_recipe(self, *_args: Any) -> None:
        self.btn_choose_env_reset.set_visible(False)
        self.env_recipe_path = None
        self.label_choose_env.set_label(self.default_string)

    def __reset_path(self, *_args: Any) -> None:
        self.btn_choose_path_reset.set_visible(False)
        self.custom_path = ""
        self.label_choose_path.set_label(_("Select an empty directory"))
        self.btn_choose_path.set_tooltip_text(None)
        self.__check_entry_name()

    def __close_dialog(self, *_args: Any) -> None:
        if (
            self._creation_task is not None
            and self.stack_create.get_visible_child_name() == "page_creating"
        ):
            if self._cancel_requested:
                return
            self.__prompt_cancel_confirmation()
            return

        self.__finalize_close()

    def __prompt_cancel_confirmation(
        self,
        _source: Optional[Gtk.Widget] = None,
    ) -> None:
        if self._cancel_requested:
            return

        def handle_response(dialog: Adw.MessageDialog, response: str) -> None:
            if response == "confirm":
                self.__cancel_creation()
            dialog.destroy()

        dialog = Adw.MessageDialog.new(
            self.window,
            _("Cancel Bottle Creation?"),
            _(
                "Cancelling now will stop the setup once the current step finishes and remove any files created so far."
            ),
        )
        dialog.add_response("keep", _("_Keep Waiting"))
        dialog.add_response("confirm", _("_Delete and Cancel"))
        dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("keep")
        dialog.set_close_response("keep")
        dialog.connect("response", handle_response)
        dialog.present()

    def __cancel_creation(self) -> None:
        if self._cancel_requested:
            return

        self._cancel_requested = True
        self.set_can_close(False)
        self.btn_cancel_creating.set_sensitive(False)
        self.btn_cancel_creating.set_label(_("Cancelling…"))

        if self._creation_task is not None:
            self._creation_task.subtitle = _("Cancelling…")

        if self._creation_job is not None:
            self._creation_job.cancel()
        if self._creation_cancel_event is not None:
            self._creation_cancel_event.set()

        self.update_output(
            _(
                "Cancellation requested. Waiting for current step to finish before cleaning up…"
            )
        )

    def __finalize_close(self) -> None:
        self.window.disconnect_by_func(self.__remove_notifications)
        self.close()

    def __clear_creation_task(self) -> None:
        if self._creation_task is None:
            return

        if self._creation_task.task_id and TaskManager.get(self._creation_task.task_id):
            TaskManager.remove(self._creation_task)

        self._creation_task = None
        self._creation_job = None
        self._creation_cancel_event = None

    def __reset_creation_steps(self) -> None:
        self._creation_steps.clear()

        child = self.steps_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.steps_list.remove(child)
            child = next_child
