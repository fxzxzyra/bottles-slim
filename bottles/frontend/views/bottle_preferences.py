# bottle_preferences.py
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

import contextlib
import os
import shlex
from gettext import gettext as _

from gi.repository import Adw, Gdk, Gtk

from bottles.backend.globals import (
    gamemode_available,
    gamescope_available,
    hdr_wsi_available,
    lsfg_vk_available,
    mangohud_available,
    obs_vkc_available,
    vkbasalt_available,
    vmtouch_available,
)
from bottles.backend.logger import Logger
from bottles.backend.managers.runtime import RuntimeManager
from bottles.backend.models.config import BottleConfig
from bottles.backend.models.enum import Arch
from bottles.backend.models.result import Result
from bottles.backend.runner import Runner
from bottles.backend.utils.display import DisplayUtils
from bottles.backend.utils.generic import is_esync_missing
from bottles.backend.utils.runners import RunnerRegistry
from bottles.backend.utils.gpu import GPUUtils, GPUVendors
from bottles.backend.utils.manager import ManagerUtils
from bottles.backend.utils.threading import RunAsync
from bottles.backend.utils.vulkan import VulkanUtils
from bottles.backend.wine.regkeys import RegKeys
from bottles.frontend.utils.common import format_runner_name
from bottles.frontend.utils.gtk import GtkUtils
from bottles.frontend.windows.display import DisplayDialog
from bottles.frontend.windows.dlloverrides import DLLOverridesDialog
from bottles.frontend.windows.drives import DrivesDialog
from bottles.frontend.windows.envvars import EnvironmentVariablesDialog
from bottles.frontend.windows.gamescope import GamescopeDialog
from bottles.frontend.windows.lsfgvk import LsfgVkDialog
from bottles.frontend.windows.mangohud import MangoHudDialog
from bottles.frontend.windows.sandbox import SandboxDialog
from bottles.frontend.windows.vkbasalt import VkBasaltDialog, vkbasalt_config_available
from bottles.frontend.windows.vmtouch import VmtouchDialog

logging = Logger()

FLATPAK_INSTALL_COMMANDS = {
    "gamescope": "flatpak install flathub org.freedesktop.Platform.VulkanLayer.gamescope//26.08",
    "hdr": "flatpak install flathub org.freedesktop.Platform.VulkanLayer.HdrWsi//26.08",
    "vkbasalt": "flatpak install flathub org.freedesktop.Platform.VulkanLayer.vkBasalt//26.08",
    "lsfg_vk": "flatpak install flathub org.freedesktop.Platform.VulkanLayer.lsfgvk//26.08",
    "mangohud": "flatpak install flathub org.freedesktop.Platform.VulkanLayer.MangoHud//26.08",
    "obsvkc": "flatpak install flathub org.freedesktop.Platform.VulkanLayer.OBSVkCapture//26.08",
}


# noinspection PyUnusedLocal
@Gtk.Template(resource_path="/com/usebottles/bottles/details-preferences.ui")
class PreferencesView(Adw.PreferencesPage):
    __gtype_name__ = "DetailsPreferences"

    # region Widgets
    btn_manage_gamescope = Gtk.Template.Child()
    btn_manage_vkbasalt = Gtk.Template.Child()
    btn_manage_lsfg_vk = Gtk.Template.Child()
    btn_manage_mangohud = Gtk.Template.Child()
    btn_manage_sandbox = Gtk.Template.Child()
    btn_manage_vmtouch = Gtk.Template.Child()
    btn_cwd_reset = Gtk.Template.Child()
    btn_cwd = Gtk.Template.Child()
    row_discrete = Gtk.Template.Child()
    row_vkbasalt = Gtk.Template.Child()
    row_lsfg_vk = Gtk.Template.Child()
    row_gamescope = Gtk.Template.Child()
    row_mangohud = Gtk.Template.Child()
    row_gamemode = Gtk.Template.Child()
    row_vmtouch = Gtk.Template.Child()
    row_obsvkc = Gtk.Template.Child()
    row_wayland = Gtk.Template.Child()
    row_hdr = Gtk.Template.Child()
    row_winebridge = Gtk.Template.Child()
    row_manage_display = Gtk.Template.Child()
    row_runtime = Gtk.Template.Child()
    row_steam_runtime = Gtk.Template.Child()
    row_cwd = Gtk.Template.Child()
    label_cwd = Gtk.Template.Child()
    row_env_variables = Gtk.Template.Child()
    row_overrides = Gtk.Template.Child()
    row_drives = Gtk.Template.Child()
    row_sandbox = Gtk.Template.Child()
    entry_name = Gtk.Template.Child()
    text_notes = Gtk.Template.Child()
    btn_save_notes = Gtk.Template.Child()
    switch_mangohud = Gtk.Template.Child()
    switch_obsvkc = Gtk.Template.Child()
    switch_vkbasalt = Gtk.Template.Child()
    switch_lsfg_vk = Gtk.Template.Child()
    switch_wayland = Gtk.Template.Child()
    switch_hdr = Gtk.Template.Child()
    switch_winebridge = Gtk.Template.Child()
    switch_gamemode = Gtk.Template.Child()
    switch_gamescope = Gtk.Template.Child()
    switch_discrete = Gtk.Template.Child()
    switch_runtime = Gtk.Template.Child()
    switch_steam_runtime = Gtk.Template.Child()
    switch_sandbox = Gtk.Template.Child()
    switch_vmtouch = Gtk.Template.Child()
    combo_runner = Gtk.Template.Child()
    combo_d7vk = Gtk.Template.Child()
    combo_dxvk = Gtk.Template.Child()
    combo_vkd3d = Gtk.Template.Child()
    combo_nvapi = Gtk.Template.Child()
    combo_latencyflex = Gtk.Template.Child()
    combo_windows = Gtk.Template.Child()
    combo_language = Gtk.Template.Child()
    combo_sync = Gtk.Template.Child()
    spin_frame_rate_limit = Gtk.Template.Child()
    spinner_d7vk = Gtk.Template.Child()
    spinner_dxvk = Gtk.Template.Child()
    spinner_vkd3d = Gtk.Template.Child()
    spinner_nvapi = Gtk.Template.Child()
    spinner_latencyflex = Gtk.Template.Child()
    spinner_runner = Gtk.Template.Child()
    spinner_windows = Gtk.Template.Child()
    spinner_display = Gtk.Template.Child()
    group_details = Gtk.Template.Child()
    str_list_languages = Gtk.Template.Child()
    str_list_runner = Gtk.Template.Child()
    str_list_d7vk = Gtk.Template.Child()
    str_list_dxvk = Gtk.Template.Child()
    str_list_vkd3d = Gtk.Template.Child()
    str_list_nvapi = Gtk.Template.Child()
    str_list_latencyflex = Gtk.Template.Child()
    str_list_windows = Gtk.Template.Child()

    # endregion

    def __update_vkbasalt_sensitivity(self):
        self.switch_vkbasalt.set_sensitive(bool(vkbasalt_available))
        self.btn_manage_vkbasalt.set_sensitive(
            bool(vkbasalt_available) and vkbasalt_config_available
        )
        if vkbasalt_available and not vkbasalt_config_available:
            self.btn_manage_vkbasalt.set_tooltip_text(
                _("Install vkbasalt-cli to edit vkBasalt settings.")
            )

    def __init__(self, details, config, **kwargs):
        super().__init__(**kwargs)

        # common variables and references
        self.window = details.window
        self.manager = details.window.manager
        self.config = config
        self.btn_save_notes.connect("clicked", self.__save_notes)
        self.text_notes.get_buffer().connect(
            "changed", self.__notes_changed
        )
        self.queue = details.queue
        self.details = details
        self.combo_runner.set_list_factory(
            GtkUtils.create_full_width_string_list_factory()
        )

        steam_runtimes = RuntimeManager.get_runtimes("steam")
        self.row_steam_runtime.set_visible(True)
        self.switch_steam_runtime.set_sensitive(bool(steam_runtimes))
        if steam_runtimes:
            self.switch_steam_runtime.connect(
                "state-set", self.__toggle_feature_cb, "use_steam_runtime"
            )
        else:
            self.row_steam_runtime.set_subtitle(
                _(
                    "Steam Runtime was not detected. Install it or grant Bottles "
                    "access to Steam files, then restart Bottles."
                )
            )

        _not_available = _("This feature is unavailable on your system.")
        _flatpak_not_available = _("{} To add this feature, please run").format(
            _not_available
        )
        self._install_commands = FLATPAK_INSTALL_COMMANDS

        is_flatpak = "FLATPAK_ID" in os.environ

        if not gamemode_available:
            self.switch_gamemode.set_tooltip_text(_not_available)
            self.__add_unavailable_indicator(self.row_gamemode, None)

        if not gamescope_available:
            _gamescope_command = self._install_commands.get("gamescope")
            _gamescope_not_available = (
                f"{_flatpak_not_available} {_gamescope_command}"
                if is_flatpak
                else _not_available
            )
            self.switch_gamescope.set_tooltip_text(_gamescope_not_available)
            self.btn_manage_gamescope.set_tooltip_text(_gamescope_not_available)
            self.__add_unavailable_indicator(
                self.row_gamescope, _gamescope_command if is_flatpak else None
            )

        if not vkbasalt_available:
            _vkbasalt_command = self._install_commands.get("vkbasalt")
            _vkbasalt_not_available = (
                f"{_flatpak_not_available} {_vkbasalt_command}"
                if is_flatpak
                else _not_available
            )
            self.switch_vkbasalt.set_tooltip_text(_vkbasalt_not_available)
            self.btn_manage_vkbasalt.set_tooltip_text(_vkbasalt_not_available)
            self.__add_unavailable_indicator(
                self.row_vkbasalt, _vkbasalt_command if is_flatpak else None
            )

        if not lsfg_vk_available:
            _lsfg_vk_command = self._install_commands.get("lsfg_vk")
            _lsfg_vk_not_available = (
                f"{_flatpak_not_available} {_lsfg_vk_command}"
                if is_flatpak
                else _not_available
            )
            self.switch_lsfg_vk.set_tooltip_text(_lsfg_vk_not_available)
            self.btn_manage_lsfg_vk.set_tooltip_text(_lsfg_vk_not_available)
            self.__add_unavailable_indicator(
                self.row_lsfg_vk, _lsfg_vk_command if is_flatpak else None
            )

        if not mangohud_available:
            _mangohud_command = self._install_commands.get("mangohud")
            _mangohud_not_available = (
                f"{_flatpak_not_available} {_mangohud_command}"
                if is_flatpak
                else _not_available
            )
            self.switch_mangohud.set_tooltip_text(_mangohud_not_available)
            self.btn_manage_mangohud.set_tooltip_text(_mangohud_not_available)
            self.__add_unavailable_indicator(
                self.row_mangohud, _mangohud_command if is_flatpak else None
            )

        if not obs_vkc_available:
            _obsvkc_command = self._install_commands.get("obsvkc")
            _obsvkc_not_available = (
                f"{_flatpak_not_available} {_obsvkc_command}"
                if is_flatpak
                else _not_available
            )
            self.switch_obsvkc.set_tooltip_text(_obsvkc_not_available)
            self.__add_unavailable_indicator(
                self.row_obsvkc, _obsvkc_command if is_flatpak else None
            )

        if not vmtouch_available:
            self.switch_vmtouch.set_tooltip_text(_not_available)
            self.__add_unavailable_indicator(self.row_vmtouch, None)

        is_nvidia_gpu = GPUUtils.is_gpu(GPUVendors.NVIDIA)
        if is_flatpak and is_nvidia_gpu and not hdr_wsi_available:
            _hdr_command = self._install_commands.get("hdr")
            _hdr_message = _(
                "Older NVIDIA drivers require HdrWsi and ENABLE_HDR_WSI=1 for HDR."
            )
            self.switch_hdr.set_tooltip_text(_hdr_message)
            self.__add_unavailable_indicator(
                self.row_hdr, _hdr_command, message=_hdr_message
            )

        # region signals
        self.row_manage_display.connect("activated", self.__show_display_settings)
        self.row_overrides.connect(
            "activated", self.__show_feature_dialog, DLLOverridesDialog
        )
        self.row_env_variables.connect(
            "activated", self.__show_feature_dialog, EnvironmentVariablesDialog
        )
        self.row_drives.connect("activated", self.__show_feature_dialog, DrivesDialog)
        self.btn_manage_gamescope.connect(
            "clicked", self.__show_feature_dialog, GamescopeDialog
        )
        self.btn_manage_vkbasalt.connect(
            "clicked", self.__show_feature_dialog, VkBasaltDialog
        )
        self.btn_manage_lsfg_vk.connect(
            "clicked", self.__show_feature_dialog, LsfgVkDialog
        )
        self.btn_manage_mangohud.connect(
            "clicked", self.__show_feature_dialog, MangoHudDialog
        )
        self.btn_manage_sandbox.connect(
            "clicked", self.__show_feature_dialog, SandboxDialog
        )
        self.btn_manage_vmtouch.connect(
            "clicked", self.__show_feature_dialog, VmtouchDialog
        )
        self.btn_cwd.connect("clicked", self.choose_cwd)
        self.btn_cwd_reset.connect("clicked", self.reset_cwd, True)
        self.switch_mangohud.connect("state-set", self.__toggle_feature_cb, "mangohud")
        self.switch_obsvkc.connect("state-set", self.__toggle_feature_cb, "obsvkc")
        self.switch_vkbasalt.connect("state-set", self.__toggle_feature_cb, "vkbasalt")
        self.switch_lsfg_vk.connect("state-set", self.__toggle_feature_cb, "lsfg_vk")
        self.switch_wayland.connect("state-set", self.__toggle_wayland)
        self.switch_hdr.connect("state-set", self.__toggle_hdr)
        self.switch_winebridge.connect(
            "state-set", self.__toggle_feature_cb, "winebridge"
        )
        self.switch_gamemode.connect("state-set", self.__toggle_feature_cb, "gamemode")
        self.switch_gamescope.connect("state-set", self.__toggle_gamescope)
        self.switch_sandbox.connect("state-set", self.__toggle_feature_cb, "sandbox")
        self.switch_discrete.connect(
            "state-set", self.__toggle_feature_cb, "discrete_gpu"
        )
        self.switch_vmtouch.connect("state-set", self.__toggle_feature_cb, "vmtouch")
        self.combo_runner.connect("notify::selected", self.__set_runner)
        self.combo_d7vk.connect("notify::selected", self.__set_d7vk)
        self.combo_dxvk.connect("notify::selected", self.__set_dxvk)
        self.combo_vkd3d.connect("notify::selected", self.__set_vkd3d)
        self.combo_nvapi.connect("notify::selected", self.__set_nvapi)
        self.combo_latencyflex.connect("notify::selected", self.__set_latencyflex)
        self.combo_windows.connect("notify::selected", self.__set_windows)
        self.combo_language.connect("notify::selected-item", self.__set_language)
        self.combo_sync.connect("notify::selected", self.__set_sync_type)
        self.spin_frame_rate_limit.connect(
            "notify::value", self.__set_frame_rate_limit
        )
        self.entry_name.connect("changed", self.__check_entry_name)
        self.entry_name.connect("apply", self.__save_name)
        # endregion

        self.__update_nvapi_visibility()

        """Toggle some utilities according to its availability"""
        self.switch_gamemode.set_sensitive(gamemode_available)
        self.switch_gamescope.set_sensitive(gamescope_available)
        self.btn_manage_gamescope.set_sensitive(gamescope_available)
        self.__update_vkbasalt_sensitivity()
        _lsfg_vk_supported = lsfg_vk_available and config.Arch != Arch.WIN32
        self.switch_lsfg_vk.set_sensitive(_lsfg_vk_supported)
        self.btn_manage_lsfg_vk.set_sensitive(_lsfg_vk_supported)
        if config.Arch == Arch.WIN32:
            _lsfg_vk_64_bit_only = _(
                "lsfg-vk only supports 64-bit Vulkan applications."
            )
            self.switch_lsfg_vk.set_tooltip_text(_lsfg_vk_64_bit_only)
            self.btn_manage_lsfg_vk.set_tooltip_text(_lsfg_vk_64_bit_only)
        self.switch_mangohud.set_sensitive(mangohud_available)
        self.btn_manage_mangohud.set_sensitive(mangohud_available)
        self.switch_obsvkc.set_sensitive(obs_vkc_available)
        self.switch_vmtouch.set_sensitive(vmtouch_available)

        vulkan_supported = VulkanUtils.check_support()
        if not vulkan_supported:
            self.switch_vkbasalt.set_sensitive(False)
            self.btn_manage_vkbasalt.set_sensitive(False)
            self.switch_lsfg_vk.set_sensitive(False)
            self.btn_manage_lsfg_vk.set_sensitive(False)
            self.switch_obsvkc.set_sensitive(False)

        is_wayland_session = DisplayUtils.display_server_type() == "wayland"
        self.switch_wayland.set_sensitive(is_wayland_session)
        self.__update_hdr_sensitivity()

    def __create_unavailable_popover(
        self, command: str | None, message: str | None = None
    ) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        unavailable_label = Gtk.Label(
            label=message or _("This feature is unavailable on your system."),
            xalign=0,
            wrap=True,
        )
        box.append(unavailable_label)

        if command:
            command_label = Gtk.Label(label=_("To add it, please run:"))
            command_label.set_xalign(0)
            box.append(command_label)

            command_box = Gtk.Box(spacing=6)
            command_box.set_hexpand(True)

            command_entry = Gtk.Entry()
            command_entry.set_editable(False)
            command_entry.set_hexpand(True)
            command_entry.set_text(command)
            command_entry.add_css_class("monospace")
            command_entry.set_width_chars(len(command))
            command_entry.set_focusable(False)

            btn_copy_command = Gtk.Button()
            btn_copy_command.set_icon_name("edit-copy-symbolic")
            btn_copy_command.set_tooltip_text(_("Copy command"))
            btn_copy_command.connect(
                "clicked", self.__copy_command_to_clipboard, command
            )

            command_box.append(command_entry)
            command_box.append(btn_copy_command)
            box.append(command_box)

        popover.set_child(box)
        return popover

    def __add_unavailable_indicator(
        self,
        row: Adw.ActionRow,
        command: str | None,
        message: str | None = None,
    ):
        if not row:
            return

        popover = self.__create_unavailable_popover(command, message)
        menu_button = Gtk.MenuButton()
        menu_button.set_valign(Gtk.Align.CENTER)
        menu_button.set_icon_name("dialog-warning-symbolic")
        menu_button.set_has_frame(False)
        menu_button.set_popover(popover)
        menu_button.set_tooltip_text(
            message or _("This feature is unavailable on your system.")
        )

        row.add_suffix(menu_button)
        return menu_button

    def __copy_command_to_clipboard(self, _widget, command: str):
        display = Gdk.Display.get_default()
        if not display:
            return

        clipboard = Gdk.Display.get_clipboard(display)
        clipboard.set_content(Gdk.ContentProvider.new_for_value(command))
        self.window.show_toast(_("Copied to clipboard"))

    def __check_entry_name(self, *_args):
        if self.entry_name.get_text() != self.config.Name:
            is_duplicate = any(config.Name == self.entry_name.get_text() for config in self.manager.local_bottles.values())
            if is_duplicate:
                self.window.show_toast(_("This container name is already in use."))
                self.__valid_name = False
                self.entry_name.add_css_class("error")
                return
        self.__valid_name = True
        self.entry_name.remove_css_class("error")

    def __save_name(self, *_args):
        if not self.__valid_name:
            self.entry_name.set_text(self.config.Name)
            self.__valid_name = True
            return

        new_name = self.entry_name.get_text()
        result = self.manager.update_config(config=self.config, key="Name", value=new_name)
        if not result.ok:
            self.window.show_toast(result.message)
            return

        self.manager.update_bottles(silent=True)  # Updates backend bottles list and UI
        self.window.page_library.update()
        self.details.view_bottle.label_name.set_text(self.config.Name)

    def choose_cwd(self, widget):
        def set_path(_dialog, response):
            if response != Gtk.ResponseType.ACCEPT:
                return

            path = dialog.get_file().get_path()

            self.manager.update_config(
                config=self.config, key="WorkingDir", value=dialog.get_file().get_path()
            )
            self.__update_working_directory_row(path)

        dialog = Gtk.FileChooserNative.new(
            title=_("Select Working Directory"),
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            parent=self.window,
        )

        dialog.set_modal(True)
        dialog.connect("response", set_path)
        dialog.show()

    def reset_cwd(self, *_args):
        self.manager.update_config(config=self.config, key="WorkingDir", value="")
        self.__update_working_directory_row()

    def __update_working_directory_row(self, working_dir=None):
        """Update the working directory."""

        working_dir = working_dir if working_dir is not None else self.config.WorkingDir
        has_custom_dir = bool(working_dir)

        if has_custom_dir:
            basename = os.path.basename(os.path.normpath(working_dir)) or working_dir
            self.label_cwd.set_label(basename)
            self.label_cwd.set_tooltip_text(working_dir)
        else:
            self.label_cwd.set_label(_("(Default)"))
            self.label_cwd.set_tooltip_text(None)

        self.btn_cwd_reset.set_visible(has_custom_dir)

    def update_combo_components(self):
        """
        This function update the components' combo boxes with the
        items in the manager catalogs. It also temporarily disable
        the functions connected to the combo boxes to avoid the
        bottle configuration to be updated during the process.
        """
        self.combo_runner.handler_block_by_func(self.__set_runner)
        self.combo_language.handler_block_by_func(self.__set_language)
        self.combo_windows.handler_block_by_func(self.__set_windows)

        for string_list in [
            self.str_list_runner,
            self.str_list_languages,
            self.str_list_windows,
        ]:
            string_list.splice(0, string_list.get_n_items())

        self._runner_ids = list(self.manager.runners_available)
        for index, runner in enumerate(self._runner_ids):
            self.str_list_runner.append(format_runner_name(runner))

        for lang in ManagerUtils.get_languages():
            self.str_list_languages.append(lang)

        self.combo_runner.handler_unblock_by_func(self.__set_runner)
        self.combo_language.handler_unblock_by_func(self.__set_language)
        self.combo_windows.handler_unblock_by_func(self.__set_windows)
        self.__refresh_component_selection()

    def __notes_changed(self, buffer):
        notes = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self.btn_save_notes.set_sensitive(notes != self.config.Notes)

    def __save_notes(self, _button):
        buffer = self.text_notes.get_buffer()
        notes = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        previous = self.config.Notes
        result = self.manager.update_config(self.config, key="Notes", value=notes)
        if not result.ok:
            self.config.Notes = previous
            self.window.show_toast(_("The notes could not be saved."))
            return
        self.config = result.data["config"]
        self.btn_save_notes.set_sensitive(False)

    def set_config(self, config: BottleConfig):
        if self.config.Id != config.Id or not self.btn_save_notes.get_sensitive():
            self.text_notes.get_buffer().set_text(config.Notes)
            self.btn_save_notes.set_sensitive(False)
        self.config = config
        parameters = self.config.Parameters
        self.__update_nvapi_visibility()

        # temporary lock functions connected to the widgets
        self.switch_mangohud.handler_block_by_func(self.__toggle_feature_cb)
        self.switch_vkbasalt.handler_block_by_func(self.__toggle_feature_cb)
        self.switch_lsfg_vk.handler_block_by_func(self.__toggle_feature_cb)
        self.switch_wayland.handler_block_by_func(self.__toggle_wayland)
        self.switch_hdr.handler_block_by_func(self.__toggle_hdr)
        self.switch_winebridge.handler_block_by_func(self.__toggle_feature_cb)
        self.switch_obsvkc.handler_block_by_func(self.__toggle_feature_cb)
        self.switch_gamemode.handler_block_by_func(self.__toggle_feature_cb)
        self.switch_gamescope.handler_block_by_func(self.__toggle_gamescope)
        self.switch_sandbox.handler_block_by_func(self.__toggle_feature_cb)
        self.switch_discrete.handler_block_by_func(self.__toggle_feature_cb)
        with contextlib.suppress(TypeError):
            self.switch_steam_runtime.handler_block_by_func(self.__toggle_feature_cb)
        self.combo_runner.handler_block_by_func(self.__set_runner)
        self.combo_d7vk.handler_block_by_func(self.__set_d7vk)
        self.combo_dxvk.handler_block_by_func(self.__set_dxvk)
        self.combo_vkd3d.handler_block_by_func(self.__set_vkd3d)
        self.combo_nvapi.handler_block_by_func(self.__set_nvapi)
        self.combo_latencyflex.handler_block_by_func(self.__set_latencyflex)
        self.combo_windows.handler_block_by_func(self.__set_windows)
        self.combo_language.handler_block_by_func(self.__set_language)
        self.spin_frame_rate_limit.handler_block_by_func(self.__set_frame_rate_limit)
        self.switch_mangohud.set_active(parameters.mangohud)
        self.switch_obsvkc.set_active(parameters.obsvkc)
        self.switch_vkbasalt.set_active(parameters.vkbasalt)
        self.switch_lsfg_vk.set_active(parameters.lsfg_vk)
        _lsfg_vk_supported = (
            lsfg_vk_available
            and config.Arch != Arch.WIN32
            and VulkanUtils.check_support()
        )
        self.switch_lsfg_vk.set_sensitive(_lsfg_vk_supported)
        self.btn_manage_lsfg_vk.set_sensitive(_lsfg_vk_supported)
        self.switch_wayland.set_active(parameters.wayland)
        self.switch_hdr.set_active(parameters.hdr)
        self.__update_hdr_sensitivity(parameters.hdr)
        self.switch_winebridge.set_active(parameters.winebridge)
        self.switch_gamemode.set_active(parameters.gamemode)
        self.switch_gamescope.set_active(parameters.gamescope)
        self.switch_sandbox.set_active(parameters.sandbox)
        self.switch_steam_runtime.set_active(parameters.use_steam_runtime)
        self.switch_vmtouch.set_active(parameters.vmtouch)
        self.spin_frame_rate_limit.set_value(parameters.frame_rate_limit)

        # self.toggle_sync.set_active(parameters["sync"] == "wine")
        # self.toggle_esync.set_active(parameters["sync"] == "esync")
        # self.toggle_fsync.set_active(parameters["sync"] == "fsync")

        self.switch_discrete.set_active(parameters.discrete_gpu)

        self.__update_working_directory_row()

        self.entry_name.set_text(config.Name)

        self.row_cwd.set_subtitle(
            _('Directory that contains the data of "{}".').format(config.Name)
        )

        self.combo_language.set_selected(
            ManagerUtils.get_languages(from_locale=self.config.Language, get_index=True)
        )

        # region Windows Versions
        # NOTE: this should not be here but it's the only way to handle windows
        # versions in the current structure, we will fix this in the future
        # with the new Bottles Backend.
        self.windows_versions = {
            "win11": "Windows 11",
            "win10": "Windows 10",
            "win81": "Windows 8.1",
            "win8": "Windows 8",
            "win7": "Windows 7",
            "win2008r2": "Windows 2008 R2",
            "win2008": "Windows 2008",
            "vista": "Windows Vista",
            "winxp": "Windows XP",
        }

        if self.config.Arch == Arch.WIN32:
            self.windows_versions["win98"] = "Windows 98"
            self.windows_versions["win95"] = "Windows 95"

        for index, windows_version in enumerate(self.windows_versions):
            self.str_list_windows.append(self.windows_versions[windows_version])
            if windows_version == self.config.Windows:
                self.combo_windows.set_selected(index)
        # endregion

        parameters = self.config.Parameters

        self.__refresh_component_selection()

        self.__select_configured_runner()

        sync_types = [
            "wine",
            "esync",
            "fsync",
            "ntsync",
        ]
        for sync in sync_types:
            if sync == parameters.sync:
                self.combo_sync.set_selected(sync_types.index(sync))

        # unlock functions connected to the widgets
        self.switch_mangohud.handler_unblock_by_func(self.__toggle_feature_cb)
        self.switch_vkbasalt.handler_unblock_by_func(self.__toggle_feature_cb)
        self.switch_lsfg_vk.handler_unblock_by_func(self.__toggle_feature_cb)
        self.switch_wayland.handler_unblock_by_func(self.__toggle_wayland)
        self.switch_hdr.handler_unblock_by_func(self.__toggle_hdr)
        self.switch_winebridge.handler_unblock_by_func(self.__toggle_feature_cb)
        self.switch_obsvkc.handler_unblock_by_func(self.__toggle_feature_cb)
        self.switch_gamemode.handler_unblock_by_func(self.__toggle_feature_cb)
        self.switch_gamescope.handler_unblock_by_func(self.__toggle_gamescope)
        self.switch_sandbox.handler_unblock_by_func(self.__toggle_feature_cb)
        self.switch_discrete.handler_unblock_by_func(self.__toggle_feature_cb)
        with contextlib.suppress(TypeError):
            self.switch_steam_runtime.handler_unblock_by_func(self.__toggle_feature_cb)
        self.combo_runner.handler_unblock_by_func(self.__set_runner)
        self.combo_d7vk.handler_unblock_by_func(self.__set_d7vk)
        self.combo_dxvk.handler_unblock_by_func(self.__set_dxvk)
        self.combo_vkd3d.handler_unblock_by_func(self.__set_vkd3d)
        self.combo_nvapi.handler_unblock_by_func(self.__set_nvapi)
        self.combo_latencyflex.handler_unblock_by_func(self.__set_latencyflex)
        self.combo_windows.handler_unblock_by_func(self.__set_windows)
        self.combo_language.handler_unblock_by_func(self.__set_language)
        self.spin_frame_rate_limit.handler_unblock_by_func(self.__set_frame_rate_limit)
        self.__update_esync_warning(parameters.sync)


    def __show_display_settings(self, widget):
        new_window = DisplayDialog(
            parent_window=self.window,
            config=self.config,
            details=self.details,
            queue=self.queue,
            widget=widget,
            spinner_display=self.spinner_display,
        )
        new_window.present()

    def __show_feature_dialog(self, _widget: Gtk.Widget, dialog: type[Adw.Window] | type[Adw.Dialog]) -> None:
        """Present dialog of a specific feature."""
        window = dialog(window=self.window, config=self.config)
        if isinstance(window, Adw.Dialog):
            window.present(self.window)
        else:
            window.present()

    def __toggle_feature(self, state: bool, key: str) -> None:
        """Toggle a specific feature."""
        self.config = self.manager.update_config(
            config=self.config, key=key, value=state, scope="Parameters"
        ).data["config"]

    def __toggle_feature_cb(self, _widget: Gtk.Widget, state: bool, key: str) -> None:
        self.__toggle_feature(state=state, key=key)

    def __toggle_wayland(self, _widget: Gtk.Widget, state: bool) -> None:
        self.__toggle_feature(state=state, key="wayland")
        self.__update_hdr_sensitivity()
        rk = RegKeys(self.config)
        RunAsync(rk.toggle_wayland_driver, state=state)

    def __toggle_hdr(self, _widget: Gtk.Widget, state: bool) -> None:
        self.__toggle_feature(state=state, key="hdr")
        self.__update_hdr_sensitivity(state)

    def __toggle_gamescope(self, _widget: Gtk.Widget, state: bool) -> None:
        self.__toggle_feature(state=state, key="gamescope")
        self.__update_hdr_sensitivity()

    def __update_nvapi_visibility(self) -> None:
        visible = GPUUtils.is_gpu(GPUVendors.NVIDIA) or self.config.Parameters.dxvk_nvapi
        self.combo_nvapi.set_visible(visible)

    def __update_hdr_sensitivity(self, active: bool | None = None) -> None:
        if active is None:
            active = self.config.Parameters.hdr
        self.switch_hdr.set_sensitive(
            active
            or (
                VulkanUtils.check_support()
                and (
                    (
                        DisplayUtils.display_server_type() == "wayland"
                        and self.config.Parameters.wayland
                    )
                    or (gamescope_available and self.config.Parameters.gamescope)
                )
            )
        )

    def __set_sync_type(self, *_args):
        """
        Set the sync type (wine, esync, fsync, ntsync)
        """
        sync_types = [
            "wine",
            "esync",
            "fsync",
            "ntsync",
        ]
        sync = sync_types[self.combo_sync.get_selected()]
        if sync == self.config.Parameters.sync:
            return

        previous = self.config.Parameters.sync
        self.queue.add_task()
        self.combo_sync.set_sensitive(False)

        def completed(result, error):
            if error or not result.ok:
                self.config.Parameters.sync = previous
                self.combo_sync.handler_block_by_func(self.__set_sync_type)
                self.combo_sync.set_selected(sync_types.index(previous))
                self.combo_sync.handler_unblock_by_func(self.__set_sync_type)
                self.window.show_toast(_("Could not change the synchronization mode."))
            else:
                self.config = result.data["config"]
            self.__update_esync_warning(self.config.Parameters.sync)
            self.combo_sync.set_sensitive(True)
            self.queue.end_task()

        RunAsync(
            self.manager.update_config,
            callback=completed,
            config=self.config,
            key="sync",
            value=sync,
            scope="Parameters",
        )

    def __update_esync_warning(self, sync):
        if not hasattr(self, "_esync_warning"):
            self._esync_warning = self.__add_unavailable_indicator(
                self.combo_sync, None,
                _("This runner has no Esync, so it will use its default."),
            )
        info = RunnerRegistry.entries.get(self.config.Runner)
        missing = info is not None and is_esync_missing(shlex.quote(info.wine_for_arch(self.config.Arch)))
        self._esync_warning.set_visible(sync == "esync" and missing)

    def __set_frame_rate_limit(self, spin_row, _pspec):
        value = int(spin_row.get_value())
        if value == self.config.Parameters.frame_rate_limit:
            return

        self.config = self.manager.update_config(
            config=self.config,
            key="frame_rate_limit",
            value=value,
            scope="Parameters",
        ).data["config"]

    def __select_configured_runner(self):
        # Call with the selection handler blocked. Missing means unselected;
        # displaying preferences must never rewrite the bottle's runner.
        selected = (
            self._runner_ids.index(self.config.Runner)
            if self.config.Runner in self._runner_ids
            else Gtk.INVALID_LIST_POSITION
        )
        self.combo_runner.set_selected(selected)

    def __set_components_busy(self, busy):
        for name in ("runner", "d7vk", "dxvk", "vkd3d", "nvapi", "latencyflex"):
            getattr(self, f"combo_{name}").set_sensitive(not busy)

    def __set_runner(self, *_args):
        """Set the runner to use for the bottle"""

        def set_widgets_status(status=True):
            self.__set_components_busy(not status)
            if status:
                self.spinner_runner.set_visible(False)
            else:
                self.spinner_runner.set_visible(True)

        @GtkUtils.run_in_main_loop
        def update(result: Result[dict], error=False):
            if isinstance(result, Result) and result.ok and isinstance(
                result.data, dict
            ):  # expecting Result[dict].data["config"]
                self.details.update_runner_label(runner)

                if "config" in result.data:
                    self.config = result.data["config"]
                self.__update_esync_warning(self.config.Parameters.sync)
                if self.config.Parameters.use_steam_runtime:
                    self.switch_steam_runtime.handler_block_by_func(
                        self.__toggle_feature_cb
                    )
                    self.switch_steam_runtime.set_active(True)
                    self.switch_steam_runtime.handler_unblock_by_func(
                        self.__toggle_feature_cb
                    )

            if error or not isinstance(result, Result) or not result.ok:
                self.combo_runner.handler_block_by_func(self.__set_runner)
                self.__select_configured_runner()
                self.combo_runner.handler_unblock_by_func(self.__set_runner)
                self.window.show_toast(_("Could not switch to the selected runner."))

            set_widgets_status(True)
            self.queue.end_task()

        index = self.combo_runner.get_selected()
        if index >= len(self._runner_ids):
            return
        runner = self._runner_ids[index]

        set_widgets_status(False)
        self.queue.add_task()
        RunAsync(
            Runner.runner_update,
            callback=update,
            config=self.config,
            manager=self.manager,
            runner=runner,
        )

    def __set_d7vk(self, *_args):
        self.__change_component("d7vk", self.set_d7vk_status)

    def __set_dxvk(self, *_args):
        self.__change_component("dxvk", self.set_dxvk_status)

    def __set_vkd3d(self, *_args):
        self.__change_component("vkd3d", self.set_vkd3d_status)

    def __set_nvapi(self, *_args):
        self.__change_component("nvapi", self.set_nvapi_status)

    def __set_latencyflex(self, *_args):
        self.__change_component("latencyflex", self.set_latencyflex_status)

    def __change_component(self, component, callback):
        selected = getattr(self, f"combo_{component}").get_selected()
        if selected == Gtk.INVALID_LIST_POSITION:
            return
        version = self._component_versions[component][selected - 1] if selected else None
        callback(pending=True)
        self.queue.add_task()
        arguments = {"config": self.config, "enabled": selected != 0, "version": version}
        RunAsync(
            task_func=self.manager.set_dll_component, callback=callback,
            component=component, **arguments,
        )

    def __refresh_component_selection(self):
        self._component_versions = {}
        for name, field, enabled_key, handler in (
            ("d7vk", "D7VK", "d7vk", self.__set_d7vk),
            ("dxvk", "DXVK", "dxvk", self.__set_dxvk),
            ("vkd3d", "VKD3D", "vkd3d", self.__set_vkd3d),
            ("nvapi", "NVAPI", "dxvk_nvapi", self.__set_nvapi),
            ("latencyflex", "LatencyFleX", "latencyflex", self.__set_latencyflex),
        ):
            versions = list(getattr(self.manager, f"{name}_available"))
            enabled = getattr(self.config.Parameters, enabled_key)
            version = getattr(self.config, field)
            if enabled and version and version not in versions:
                versions.append(version)
            self._component_versions[name] = versions
            combo = getattr(self, f"combo_{name}")
            model = getattr(self, f"str_list_{name}")
            combo.handler_block_by_func(handler)
            model.splice(0, model.get_n_items(), [_("Disabled"), *versions])
            combo.set_selected(versions.index(version) + 1 if enabled and version in versions else 0)
            combo.handler_unblock_by_func(handler)

    def __set_windows(self, *_args):
        """Set the Windows version to use for the bottle"""

        # self.manager.dxvk_available[self.combo_dxvk.get_selected()]
        @GtkUtils.run_in_main_loop
        def update(result, error=False):
            if error:
                versions = list(self.windows_versions)
                selected = 0
                if self.config.Windows in versions:
                    selected = versions.index(self.config.Windows)
                self.combo_windows.handler_block_by_func(self.__set_windows)
                self.combo_windows.set_selected(selected)
                self.combo_windows.handler_unblock_by_func(self.__set_windows)
            else:
                self.config = self.manager.update_config(
                    config=self.config, key="Windows", value=windows_version
                ).data["config"]
            self.spinner_windows.set_visible(False)
            self.combo_windows.set_sensitive(True)
            self.queue.end_task()

        self.queue.add_task()
        self.spinner_windows.set_visible(True)
        self.combo_windows.set_sensitive(False)
        rk = RegKeys(self.config)

        for index, windows_version in enumerate(self.windows_versions):
            if self.combo_windows.get_selected() == index:
                RunAsync(rk.lg_set_windows, callback=update, version=windows_version)
                break

    def __set_language(self, *_args):
        """Set the language to use for the bottle"""
        index = self.combo_language.get_selected()
        language = ManagerUtils.get_languages(from_index=index)
        self.config = self.manager.update_config(
            config=self.config,
            key="Language",
            value=language[0],
        ).data["config"]

    def __set_component_status(self, component, status, error, pending):
        self.__set_components_busy(pending)
        getattr(self, f"spinner_{component}").set_visible(pending)
        if pending:
            return
        if error or not status.ok:
            message = str(error) if error else status.message
            self.window.show_toast(message or _("Failed to update {component}").format(component=component.upper()))
        else:
            self.config = status.data["config"]
        self.__refresh_component_selection()
        self.queue.end_task()

    @GtkUtils.run_in_main_loop
    def set_d7vk_status(self, status=None, error=None, pending=False):
        self.__set_component_status("d7vk", status, error, pending)

    @GtkUtils.run_in_main_loop
    def set_dxvk_status(self, status=None, error=None, pending=False):
        self.__set_component_status("dxvk", status, error, pending)

    @GtkUtils.run_in_main_loop
    def set_vkd3d_status(self, status=None, error=None, pending=False):
        self.__set_component_status("vkd3d", status, error, pending)

    @GtkUtils.run_in_main_loop
    def set_nvapi_status(self, status=None, error=None, pending=False):
        self.__set_component_status("nvapi", status, error, pending)

    @GtkUtils.run_in_main_loop
    def set_latencyflex_status(self, status=None, error=None, pending=False):
        self.__set_component_status("latencyflex", status, error, pending)
