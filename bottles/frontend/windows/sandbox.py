# sandbox.py
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

from gi.repository import Adw, Gtk

from bottles.backend.managers.sandbox import SandboxManager
from bottles.backend.utils.hidraw import configure_hidraw, list_hidraw_devices, normalize_hidraw_id
from bottles.backend.utils.threading import RunAsync


@Gtk.Template(resource_path="/com/usebottles/bottles/dialog-sandbox.ui")
class SandboxDialog(Adw.Window):
    __gtype_name__ = "SandboxDialog"

    # region Widgets
    switch_net = Gtk.Template.Child()
    switch_sound = Gtk.Template.Child()
    row_input = Gtk.Template.Child()
    switch_input = Gtk.Template.Child()
    row_usb = Gtk.Template.Child()
    switch_usb = Gtk.Template.Child()
    group_hidraw = Gtk.Template.Child()

    # endregion

    def __init__(self, window, config, **kwargs):
        super().__init__(**kwargs)
        self.set_transient_for(window)

        # common variables and references
        self.window = window
        self.manager = window.manager
        self.config = config
        self.__updating_device_rows = False
        self.__update(config)

        # connect signals
        self.switch_net.connect("state-set", self.__set_flag, "share_net")
        self.switch_sound.connect("state-set", self.__set_flag, "share_sound")
        self.switch_input.connect("state-set", self.__set_flag, "share_input")
        self.switch_usb.connect("state-set", self.__set_flag, "share_usb")

    def __set_flag(self, widget, state, flag):
        if self.__updating_device_rows:
            return
        self.config = self.manager.update_config(
            config=self.config, key=flag, value=state, scope="Sandbox"
        ).data["config"]

    def __set_hidraw_device(self, row, _pspec, identifier):
        previous = {
            identifier for value in self.config.Parameters.hidraw_devices
            if (identifier := normalize_hidraw_id(value))
        }
        selected = previous.copy()
        if row.get_active():
            selected.add(identifier)
        else:
            selected.discard(identifier)
        self.group_hidraw.set_sensitive(False)

        def completed(result, error=False):
            if not error and result is not None and result.ok:
                result = self.manager.update_config(
                    config=self.config, key="hidraw_devices", value=sorted(selected), scope="Parameters",
                )
            if not error and result is not None and result.ok:
                self.config = result.data["config"]
                self.__update_device_permissions()
            else:
                row.handler_block_by_func(self.__set_hidraw_device)
                row.set_active(identifier in previous)
                row.handler_unblock_by_func(self.__set_hidraw_device)
                message = str(error) if error else (result.message if result else "")
                self.window.show_toast(message or _("Could not update Wine HIDRAW preferences"))
            self.group_hidraw.set_sensitive(True)

        RunAsync(configure_hidraw, callback=completed, config=self.config, identifiers=sorted(selected))

    def __populate_hidraw_devices(self):
        devices = {device.identifier: device for device in list_hidraw_devices()}
        selected = {
            normalized
            for value in self.config.Parameters.hidraw_devices
            if (normalized := normalize_hidraw_id(value))
        }
        identifiers = list(devices)
        identifiers.extend(sorted(selected.difference(devices)))

        if not identifiers:
            self.group_hidraw.add(
                Adw.ActionRow(
                    title=_("No HIDRAW devices found"),
                    subtitle=_("Connect a flight controller and reopen this dialog."),
                )
            )
            return

        sandbox_supported = (
            not self.config.Parameters.sandbox
            or SandboxManager.supports_hidraw_devices()
        )
        if not sandbox_supported:
            self.group_hidraw.set_description(
                _("HIDRAW access is unavailable in a dedicated sandbox on this system.")
            )

        for identifier in identifiers:
            device = devices.get(identifier)
            row = Adw.SwitchRow(
                use_markup=False,
                title=device.name if device else identifier,
                subtitle=identifier if device else _("Not currently connected"),
                active=identifier in selected,
                sensitive=sandbox_supported,
            )
            row.connect("notify::active", self.__set_hidraw_device, identifier)
            self.group_hidraw.add(row)

    def __update_device_permissions(self):
        hidraw_required = (
            bool(self.config.Parameters.hidraw_devices)
            and self.config.Parameters.sandbox
            and SandboxManager.supports_hidraw_devices()
        )
        self.__updating_device_rows = True
        self.switch_input.set_active(
            self.config.Sandbox.share_input or hidraw_required
        )
        self.switch_usb.set_active(self.config.Sandbox.share_usb or hidraw_required)
        self.switch_input.set_sensitive(
            SandboxManager.supports_input_devices() and not hidraw_required
        )
        self.switch_usb.set_sensitive(
            SandboxManager.supports_usb_devices() and not hidraw_required
        )
        self.__updating_device_rows = False

    def __update(self, config):
        self.switch_net.set_active(config.Sandbox.share_net)
        self.switch_sound.set_active(config.Sandbox.share_sound)
        self.__populate_hidraw_devices()
        self.__update_device_permissions()
        if not SandboxManager.supports_input_devices():
            self.row_input.set_sensitive(False)
            self.row_input.set_subtitle(
                _("Input devices cannot be shared on this system.")
            )
        if not SandboxManager.supports_usb_devices():
            self.row_usb.set_sensitive(False)
            self.row_usb.set_subtitle(_("USB devices cannot be shared on this system."))
